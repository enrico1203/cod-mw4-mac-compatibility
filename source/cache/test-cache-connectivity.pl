#!/usr/bin/perl
use strict;
use warnings;
use utf8;
use Cwd qw(abs_path);
use File::Basename qw(dirname);
use File::Path qw(make_path);
use File::Temp qw(tempdir);
use JSON::PP;
use Test::More;

my$module=shift@ARGV // dirname(abs_path(__FILE__)).'/SP26CacheConnectivity.pm';
require $module;
my$root=tempdir('cache-tests-XXXXXX',DIR=>(shift@ARGV // '/private/tmp'),CLEANUP=>0);
my$count=0;
sub put {my($p,$b)=@_;open my$f,'>:raw',$p or die$!;print $f $b;close$f or die$!;}
sub get {my($p)=@_;open my$f,'<:raw',$p or die$!;local$/;return <$f>//'';}
sub fixture {
 my($ini)=@_;my$r="$root/case-".++$count;make_path("$r/sp26/steam_settings","$r/xpak_cache");
 put("$r/sp26/steam_settings/configs.main.ini",$ini) if defined$ini;
 put("$r/xpak_cache/test.xpak","\x00CACHE\xff\x01");
 return ("$r/sp26","$r/Backup");
}
sub rejects {my($name,$f)=@_;my$ok=eval{$f->();1;};ok(!$ok,$name);}
sub without_parent {
 my($ini)=@_;my($game,$backup)=fixture($ini);
 unlink(dirname($game).'/xpak_cache/test.xpak') or die$!;
 rmdir(dirname($game).'/xpak_cache') or die$!;
 return($game,$backup);
}

my@text_cases=(
 ['old single key',"[main::connectivity]\noffline=1\n","[main::connectivity]\noffline=0\ndisable_lan_only=1\n"],
 ['both values',"[main::connectivity]\noffline=1\ndisable_lan_only=0\n","[main::connectivity]\noffline=0\ndisable_lan_only=1\n"],
 ['CRLF BOM and unrelated section',"\xef\xbb\xbf[main::connectivity]\r\n OFFLINE = 1 ; keep\r\n[other]\r\nname=caf\xc3\xa9\r\n","\xef\xbb\xbf[main::connectivity]\r\n OFFLINE = 0 ; keep\r\ndisable_lan_only=1\r\n[other]\r\nname=caf\xc3\xa9\r\n"],
 ['missing section',"[other]\nkeep=true","[other]\nkeep=true\n[main::connectivity]\noffline=0\ndisable_lan_only=1\n"],
 ['empty file','',"[main::connectivity]\noffline=0\ndisable_lan_only=1\n"],
 ['no final newline',"[main::connectivity]\noffline=1","[main::connectivity]\noffline=0\ndisable_lan_only=1\n"],
 ['existing correct bytes',"[MAIN::Connectivity] ; heading\nDisable_Lan_Only=1 # keep\noffline=0","[MAIN::Connectivity] ; heading\nDisable_Lan_Only=1 # keep\noffline=0"],
 ['last section',"[a]\nkeep=1\n[main::connectivity]\n; note\n","[a]\nkeep=1\n[main::connectivity]\n; note\noffline=0\ndisable_lan_only=1\n"],
);
for my$c(@text_cases){is(SP26CacheConnectivity::proposed($c->[1]),$c->[2],"text: $c->[0]");}
for my$c(
 ['duplicate key',"[main::connectivity]\noffline=1\nOFFLINE=0\n"],
 ['duplicate section',"[main::connectivity]\n[MAIN::Connectivity]\n"],
 ['malformed key',"[main::connectivity]\noffline: 1\n"],
 ['malformed heading',"[main::connectivity] junk\noffline=1\n"],
 ['UTF16',"\xff\xfe[\x00m\x00"],
 ['invalid UTF8',"\xff"],
 ['bare CR',"[main::connectivity]\roffline=1\r"],
){rejects("reject $c->[0]",sub{SP26CacheConnectivity::proposed($c->[1])});}

{
 my($game,$backup)=fixture("[main::connectivity]\noffline=1\n[other]\nkeep=7\n");
 my$ini="$game/steam_settings/configs.main.ini";chmod 0640,$ini;my$old=get($ini);
 my$p=SP26CacheConnectivity::plan($game);my$r=SP26CacheConnectivity::apply($p,$backup);
 ok($r->{changed},'clean setup applied');ok($r->{after}{settings_ready} && $r->{after}{cache_link_ready},'both settings and cache link ready');
 is(get("$r->{backup}/configs.main.before.ini"),$old,'original INI backed up byte for byte');
 is((stat($ini))[2]&0777,0640,'INI mode preserved');
 is(readlink("$game/xpak_cache"),'../xpak_cache','relative link points to parent cache');
 is(get("$game/xpak_cache/test.xpak"),"\x00CACHE\xff\x01",'cache content unchanged through link');
 my@before=lstat($ini);my@link_before=lstat("$game/xpak_cache");
 my$r2=SP26CacheConnectivity::apply(SP26CacheConnectivity::plan($game),$backup);
 ok(!$r2->{changed} && !exists$r2->{backup},'repeat install is a no-op without new backup');
 is((lstat($ini))[1],$before[1],'repeat install does not replace INI');
 is((lstat("$game/xpak_cache"))[1],$link_before[1],'repeat install does not replace link');
}
{
 my($game,$backup)=fixture(undef);my$r=SP26CacheConnectivity::apply(SP26CacheConnectivity::plan($game),$backup);
 ok($r->{after}{settings_ready},'missing INI created');
 is(get("$r->{backup}/configs.main.before.ini"),'','missing INI backup is empty with presence metadata');
}
{
 my($game,$backup)=fixture("[main::connectivity]\noffline=0\ndisable_lan_only=1\n");
 my$ini="$game/steam_settings/configs.main.ini";my$inode=(stat($ini))[1];
 my$r=SP26CacheConnectivity::apply(SP26CacheConnectivity::plan($game),$backup);
 ok($r->{changed},'only missing link is created');is((stat($ini))[1],$inode,'correct INI never rewritten');
}
{
 my($game)=fixture("[main::connectivity]\noffline=1\n");make_path("$game/xpak_cache");put("$game/xpak_cache/keep",'retain');
 rejects('existing cache directory rejected',sub{SP26CacheConnectivity::plan($game)});
 is(get("$game/xpak_cache/keep"),'retain','conflicting cache directory content retained');
 is(get("$game/steam_settings/configs.main.ini"),"[main::connectivity]\noffline=1\n",'conflict leaves INI unchanged');
}
for my$kind(qw(dangling wrong file)){
 my($game)=fixture('');
 if($kind eq 'file'){put("$game/xpak_cache",'retain');}else{symlink($kind eq 'dangling'?'../absent':'steam_settings',"$game/xpak_cache") or die$!;}
 rejects("conflicting cache $kind rejected",sub{SP26CacheConnectivity::plan($game)});
 ok(-e"$game/xpak_cache" || -l"$game/xpak_cache","conflicting cache $kind retained");
}
{
 my($game,$backup)=without_parent(undef);my$cache=dirname($game).'/xpak_cache';
 my$p=SP26CacheConnectivity::plan($game);
 ok(!$p->{cache_exists} && !-e$cache,'planning a first launch does not create the missing cache');
 my$r=SP26CacheConnectivity::apply($p,$backup);
 ok(-d$cache && !-l$cache,'missing parent cache folder created');
 ok($r->{after}{cache_directory_ready} && $r->{after}{cache_link_ready},'first launch cache and link both ready');
 is(readlink("$game/xpak_cache"),'../xpak_cache','first launch link points to new cache');
 opendir my$d,$cache or die$!;my@files=grep{$_ ne '.' && $_ ne '..'}readdir$d;closedir$d;
 is(scalar@files,0,'new cache starts empty');
 my$inode=(stat($cache))[1];my$r2=SP26CacheConnectivity::apply(SP26CacheConnectivity::plan($game),$backup);
 ok(!$r2->{changed},'repeat first-launch preparation is a no-op');
 is((stat($cache))[1],$inode,'new cache is reused on the next launch');
}
{
 my($game,$backup)=without_parent("[main::connectivity]\noffline=0\ndisable_lan_only=1\n");
 symlink('../xpak_cache',"$game/xpak_cache") or die$!;my$inode=(lstat("$game/xpak_cache"))[1];
 my$p=SP26CacheConnectivity::plan($game);
 ok(!SP26CacheConnectivity::summary($p)->{cache_link_ready},'expected dangling link is not reported ready before folder creation');
 SP26CacheConnectivity::apply($p,$backup);
 ok(-d"$game/xpak_cache",'creating the missing folder repairs an existing expected link');
 is((lstat("$game/xpak_cache"))[1],$inode,'expected existing link is not replaced');
}
for my$kind(qw(file symlink)){
 my($game)=without_parent('');my$cache=dirname($game).'/xpak_cache';
 if($kind eq 'file'){put($cache,'retain');}else{symlink('sp26/steam_settings',$cache) or die$!;}
 rejects("conflicting parent cache $kind retained",sub{SP26CacheConnectivity::plan($game)});
 ok(-e$cache || -l$cache,"parent cache $kind still exists");
}
{
 my($game,$backup)=without_parent("[main::connectivity]\noffline=1\n");my$p=SP26CacheConnectivity::plan($game);
 {no warnings 'redefine';local*SP26CacheConnectivity::_atomic_write=sub{die "injected write failure\n";};
  rejects('first-launch write failure reported',sub{SP26CacheConnectivity::apply($p,$backup)});}
 is(get("$game/steam_settings/configs.main.ini"),$p->{before},'first-launch failure preserves INI');
 ok(!-e"$game/xpak_cache" && !-l"$game/xpak_cache",'first-launch failure removes only the new link');
 ok(!-e(dirname($game).'/xpak_cache'),'first-launch failure removes its own empty cache folder');
}
{
 my($game,$backup)=without_parent("[main::connectivity]\noffline=1\n");my$p=SP26CacheConnectivity::plan($game);my$cache=dirname($game).'/xpak_cache';
 {no warnings 'redefine';local*SP26CacheConnectivity::_atomic_write=sub{put("$cache/new-data.xpak",'keep new data');die "injected write failure\n";};
  rejects('failure after new cache receives data reported',sub{SP26CacheConnectivity::apply($p,$backup)});}
 is(get("$cache/new-data.xpak"),'keep new data','rollback preserves any data added to the new cache');
 ok(!-e"$game/xpak_cache" && !-l"$game/xpak_cache",'rollback still removes its own new link');
 my($transaction)=glob("$backup/cache-connectivity-*/transaction.json");
 is(JSON::PP->new->decode(get($transaction))->{state},'rolled-back-cache-retained','retained populated cache recorded explicitly');
}
{
 my($game,$backup)=without_parent('');my$p=SP26CacheConnectivity::plan($game);my$cache=dirname($game).'/xpak_cache';
 mkdir$cache or die$!;put("$cache/other-process-data",'retain');
 rejects('parent cache created after planning is preserved',sub{SP26CacheConnectivity::apply($p,$backup)});
 is(get("$cache/other-process-data"),'retain','concurrent cache data untouched');
}
for my$kind(qw(symlink hardlink)){
 my($game)=fixture('original');my$ini="$game/steam_settings/configs.main.ini";my$other=dirname($game).'/original.ini';rename($ini,$other) or die$!;
 if($kind eq 'symlink'){symlink($other,$ini) or die$!;}else{link($other,$ini) or die$!;}
 rejects("INI $kind rejected",sub{SP26CacheConnectivity::plan($game)});is(get($other),'original',"INI $kind target retained");
}
{
 my($game)=fixture('');my$s="$game/steam_settings";rename($s,"$s-old") or die$!;symlink('steam_settings-old',$s) or die$!;
 rejects('linked settings directory rejected',sub{SP26CacheConnectivity::plan($game)});
}
{
 my($game,$backup)=fixture("[main::connectivity]\noffline=1\n");my$p=SP26CacheConnectivity::plan($game);
 put("$game/steam_settings/configs.main.ini",'later edit');
 rejects('stale prepared state rejected',sub{SP26CacheConnectivity::apply($p,$backup)});
 is(get("$game/steam_settings/configs.main.ini"),'later edit','later user edit retained');
 ok(!-e"$game/xpak_cache" && !-l"$game/xpak_cache",'stale plan creates no link');
}
{
 my($game,$backup)=fixture("[main::connectivity]\noffline=1\n");my$p=SP26CacheConnectivity::plan($game);
 {no warnings 'redefine';local*SP26CacheConnectivity::_atomic_write=sub{die "injected write failure\n";};
  rejects('write failure reported',sub{SP26CacheConnectivity::apply($p,$backup)});}
 is(get("$game/steam_settings/configs.main.ini"),$p->{before},'write failure retains original INI');
 ok(!-e"$game/xpak_cache" && !-l"$game/xpak_cache",'write failure removes only newly created link');
}
{
 my($game,$backup)=fixture("[main::connectivity]\noffline=1\n");my$p=SP26CacheConnectivity::plan($game);
 my$real=\&SP26CacheConnectivity::plan;my$calls=0;
 {no warnings 'redefine';local*SP26CacheConnectivity::plan=sub{die "injected readback failure\n" if ++$calls==3;return $real->(@_);};
  rejects('post-write readback failure reported',sub{SP26CacheConnectivity::apply($p,$backup)});}
 is(get("$game/steam_settings/configs.main.ini"),$p->{before},'readback failure rolls back INI');
 ok(!-e"$game/xpak_cache" && !-l"$game/xpak_cache",'readback failure rolls back new link');
}
note("Fixture evidence: $root");
done_testing();

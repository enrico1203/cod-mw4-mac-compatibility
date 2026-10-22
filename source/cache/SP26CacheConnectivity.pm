package SP26CacheConnectivity;
use strict;
use warnings;
use utf8;
use Cwd qw(abs_path);
use Digest::SHA qw(sha256_hex);
use Encode qw(decode FB_CROAK);
use File::Basename qw(dirname);
use File::Path qw(make_path);
use File::Temp qw(tempdir tempfile);
use JSON::PP;

sub _read {
 my($path)=@_;open my$f,'<:raw',$path or die "Could not read the connectivity settings.\n";
 local$/;return <$f> // '';
}
sub _write {
 my($path,$bytes)=@_;open my$f,'>:raw',$path or die "Could not write the settings backup.\n";
 print $f $bytes or die "Could not write the settings backup.\n";close$f or die "Could not save the settings backup.\n";
}
sub proposed {
 my($bytes)=@_;my$validation=$bytes;decode('UTF-8',$validation,FB_CROAK);
 die "The INI text format is not supported.\n" if $bytes=~/\x00|\r(?!\n)/;
 my$bom=$bytes=~s/^\xef\xbb\xbf// ? "\xef\xbb\xbf" : '';
 my$newline=$bytes=~/\r\n/ ? "\r\n" : "\n";
 my@lines=split /(?<=\n)/,$bytes;my($inside,$sections,$insert)=(0,0,scalar@lines);
 my%found;my%wanted=(offline=>'0',disable_lan_only=>'1');
 for my$i(0..$#lines){
  my$line=$lines[$i];
  if($line=~/^[ \t]*\[([^\]\r\n]+)\][ \t]*(?:[;#][^\r\n]*)?(?:\r?\n)?\z/){
   $insert=$i if $inside;my$section=lc$1;$section=~s/^[ \t]+|[ \t]+$//g;
   $inside=$section eq 'main::connectivity';
   die "Duplicate connectivity section in the INI. The file was preserved.\n" if $inside && ++$sections>1;
   next;
  }
  die "Unrecognized INI section header. The file was preserved.\n" if $line=~/^[ \t]*\[/;
  next unless $inside;
  if($line=~/^([ \t]*)(offline|disable_lan_only)([ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?\z/i){
   my($lead,$key,$equals,$value,$end)=($1,$2,$3,$4,$5//'');my$name=lc$key;
   die "Duplicate connectivity setting in the INI. The file was preserved.\n" if $found{$name}++;
   my$comment=$value=~/([ \t]+[;#].*)\z/ ? $1 : '';
   $lines[$i]=$lead.$key.$equals.$wanted{$name}.$comment.$end;
  }elsif($line=~/^[ \t]*(?:offline|disable_lan_only)\b/i){
   die "Unrecognized INI connectivity setting. The file was preserved.\n";
  }
 }
 if(!$sections){
  $lines[-1].=$newline if @lines && $lines[-1]!~/\n\z/;
  push @lines,'[main::connectivity]'.$newline;
  push @lines,map{$_.'='.$wanted{$_}.$newline}qw(offline disable_lan_only);
 }else{
  my@missing=map{$_.'='.$wanted{$_}.$newline}grep{!$found{$_}}qw(offline disable_lan_only);
  if(@missing){$lines[$insert-1].=$newline if $insert && $lines[$insert-1]!~/\n\z/;splice @lines,$insert,0,@missing;}
 }
 return $bom.join('',@lines);
}
sub plan {
 my($game)=@_;$game=abs_path($game) // die "Game folder not found.\n";
 my$settings="$game/steam_settings";my$ini="$settings/configs.main.ini";
 my$cache=dirname($game).'/xpak_cache';my$link="$game/xpak_cache";
 die "The steam_settings folder is missing or is a link. Files were preserved.\n" unless -d$settings && !-l$settings;
 my$cache_exists=-e$cache || -l$cache;
 die "The parent xpak_cache path is not a regular folder. It was preserved.\n" if $cache_exists && (!-d$cache || -l$cache);
 my$exists=-e$ini || -l$ini;my@stat=lstat($ini);
 die "The INI is not a regular file with a single link. It was preserved.\n" if $exists && (!-f$ini || -l$ini || $stat[3]!=1);
 my$before=$exists ? _read($ini) : '';my$after=proposed($before);
 my$link_exists=-e$link || -l$link;
 my$expected_link=$link_exists && -l$link && (readlink($link) eq '../xpak_cache' || readlink($link) eq $cache
  || ($cache_exists && -d$link && (abs_path($link)//'') eq abs_path($cache)));
 die "sp26/xpak_cache already exists as a different folder or link. Its contents were preserved.\n" if $link_exists && !$expected_link;
 return {game=>$game,ini=>$ini,cache=>$cache,link=>$link,ini_exists=>$exists?1:0,
  before=>$before,after=>$after,mode=>$exists?($stat[2]&0777):0600,
  file_id=>$exists?join(':',@stat[0,1,2,3]):'',cache_exists=>$cache_exists?1:0,
  link_exists=>$link_exists?1:0,link_target=>$link_exists?readlink($link):undef};
}
sub summary {
 my($p)=@_;return {ini_exists=>$p->{ini_exists},ini_sha256=>sha256_hex($p->{before}),
  settings_ready=>$p->{ini_exists} && $p->{before} eq $p->{after} ? JSON::PP::true:JSON::PP::false,
  cache_directory_ready=>$p->{cache_exists}?JSON::PP::true:JSON::PP::false,
  cache_link_ready=>$p->{cache_exists} && $p->{link_exists}?JSON::PP::true:JSON::PP::false};
}
sub _same_plan {
 my($a,$b)=@_;
 for my$key(qw(game ini_exists before after mode file_id cache_exists link_exists link_target)){
  return 0 if ($a->{$key}//'') ne ($b->{$key}//'');
 }return 1;
}
sub _atomic_write {
 my($path,$bytes,$mode)=@_;my($f,$temp)=tempfile('.sp26-settings-XXXXXX',DIR=>dirname($path),UNLINK=>0);
 my$ok=eval{binmode$f;print $f $bytes or die "Could not write the settings.\n";close$f or die "Could not save the settings.\n";
  chmod($mode,$temp)==1 or die "Could not preserve the settings permissions.\n";
  rename($temp,$path) or die "Could not replace the settings file.\n";1;};my$error=$@;
 unlink$temp if -e$temp;die$error unless $ok;
}
sub apply {
 my($p,$backups)=@_;die "The settings or cache link changed after preparation. Files were preserved.\n" unless _same_plan($p,plan($p->{game}));
 my$changed=!$p->{ini_exists} || $p->{before} ne $p->{after} || !$p->{link_exists} || !$p->{cache_exists};
 return {changed=>JSON::PP::false,after=>summary($p)} unless $changed;
 make_path($backups);my$out=tempdir('cache-connectivity-XXXXXX',DIR=>$backups,CLEANUP=>0);
 my$json=JSON::PP->new->utf8->canonical->pretty;
 _write("$out/configs.main.before.ini",$p->{before});_write("$out/configs.main.after.ini",$p->{after});
 my$report={state=>'prepared',game=>$p->{game},before=>summary($p),ini_was_present=>$p->{ini_exists},
  link_was_present=>$p->{link_exists},cache_was_present=>$p->{cache_exists},link_target=>'../xpak_cache',after_ini_sha256=>sha256_hex($p->{after})};
 _write("$out/transaction.json",$json->encode($report));
 my($created,$written,$cache_created)=(0,0,0);my$cache_id='';
 my$ok=eval{
  die "The settings or cache link changed after preparation. Files were preserved.\n" unless _same_plan($p,plan($p->{game}));
  if(!$p->{cache_exists}){
   mkdir($p->{cache}) or die "Could not create the cache folder.\n";
   $cache_created=1;my@id=lstat($p->{cache});$cache_id=join(':',@id[0,1]);
  }
  if(!$p->{link_exists}){symlink('../xpak_cache',$p->{link}) or die "Could not create the cache link.\n";$created=1;}
  if(!$p->{ini_exists} || $p->{before} ne $p->{after}){_atomic_write($p->{ini},$p->{after},$p->{mode});$written=1;}
  my$after=plan($p->{game});die "Connectivity setup readback verification failed.\n" unless $after->{ini_exists} && $after->{before} eq $p->{after} && $after->{link_exists} && $after->{cache_exists};
  $report->{after}=summary($after);1;
 };my$error=$@;
 if(!$ok){
  my$rollback=eval{
   if($written){die "The INI changed after setup. The backup was preserved.\n" if -l$p->{ini} || !-f$p->{ini} || _read($p->{ini}) ne $p->{after};
    if($p->{ini_exists}){_atomic_write($p->{ini},$p->{before},$p->{mode});}else{unlink$p->{ini} or die "Could not roll back the new INI.\n";}}
   if($created){die "The cache link changed after setup. The backup was preserved.\n" unless -l$p->{link} && readlink($p->{link}) eq '../xpak_cache';unlink$p->{link} or die "Could not roll back the new cache link.\n";}
   if($cache_created){
    my@id=lstat($p->{cache});
    if(-d$p->{cache} && !-l$p->{cache} && join(':',@id[0,1]) eq $cache_id){
     $report->{created_cache_retained}=JSON::PP::true unless rmdir($p->{cache});
    }else{$report->{created_cache_retained}=JSON::PP::true;}
   }
   1;
  };$report->{state}=$rollback?($report->{created_cache_retained}?'rolled-back-cache-retained':'rolled-back'):'needs-review';$report->{error}=$error;$report->{rollback_error}=$@ unless $rollback;
  _write("$out/transaction.json",$json->encode($report));die $error."Settings backup: $out\n";
 }
 $report->{state}='applied';_write("$out/transaction.json",$json->encode($report));
 return {changed=>JSON::PP::true,backup=>$out,after=>$report->{after}};
}
sub best_effort {
 my($game,$backups)=@_;
 my$report={optional=>JSON::PP::true};
 my@actions=(
  ['connectivity',sub {
   my$settings="$game/steam_settings";my$ini="$settings/configs.main.ini";
   return {state=>'skipped',reason=>'Connectivity settings are absent or use a different layout.'}
    unless -d$settings && !-l$settings && -f$ini && !-l$ini;
   my@before_id=lstat($ini);
   return {state=>'skipped',reason=>'Connectivity settings have multiple filesystem links.'} unless $before_id[3]==1;
   my$before=_read($ini);my$after=proposed($before);
   return {state=>'ready'} if $before eq $after;
   make_path($backups);
   my$out=tempdir('connectivity-XXXXXX',DIR=>$backups,CLEANUP=>0);
   _write("$out/configs.main.before.ini",$before);
   _write("$out/configs.main.after.ini",$after);
   my@now=lstat($ini);
   die "Connectivity settings changed during preparation. They were preserved.\n"
    unless -f$ini && !-l$ini && join(':',@before_id[0,1,2,3]) eq join(':',@now[0,1,2,3]) && _read($ini) eq $before;
   _atomic_write($ini,$after,$before_id[2]&0777);
   die "Connectivity settings could not be verified. Backup: $out\n" unless _read($ini) eq $after;
   return {state=>'applied',backup=>$out};
  }],
  ['cache',sub {
   my$cache=dirname($game).'/xpak_cache';my$link="$game/xpak_cache";
   return {state=>'skipped',reason=>'The parent cache folder is absent or uses a different layout.'}
    unless -d$cache && !-l$cache;
   if(-e$link || -l$link){
    return {state=>'ready'} if -l$link && -d$link && (abs_path($link)//'') eq (abs_path($cache)//'');
    return {state=>'skipped',reason=>'The existing cache path was preserved.'};
   }
   symlink('../xpak_cache',$link) or die "Could not create the optional cache link.\n";
   die "The optional cache link could not be verified.\n" unless -l$link && -d$link && (abs_path($link)//'') eq abs_path($cache);
   return {state=>'applied'};
  }]
 );
 for my$action(@actions){
  my($name,$operation)=@$action;
  my$result=eval{$operation->()};my$error=$@;
  if($error){$error=~s/\s+\z//;$result={state=>'failed',reason=>$error};}
  $report->{$name}=$result;
 }
 return $report;
}
1;

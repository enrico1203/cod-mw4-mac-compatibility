/* One-time read-only native identity/code check after audio initialization. */
static void observe_audio_ring(void){
 if(!R.audio_routed||R.audio_observed)return;
 QWORD table=0,method=0;if(!rd(R.audio_base+0x28048,&table,8)||!table)return;
 if(!rd(table+12*8,&method,8)||method<0x2120)return;
 QWORD base=method-0x2120;DWORD header[8];
 if(table!=base+0xb350||!rd(base,header,sizeof header)||header[0]!=0xfeedfacf||header[1]!=0x1000007||
    header[3]!=6||!header[4]||header[4]>512||header[5]>65536){line("AUDIO_NATIVE_IDENTITY_UNRESOLVED");R.audio_observed=1;return;}
 static const BYTE expected_uuid[]={0xaf,0x16,0x19,0x4c,0x7d,0xbd,0x39,0x2a,0x9b,0x3d,0x36,0x2e,0xb1,0x9d,0x60,0x1d};
 DWORD offset=32,limit=32+header[5];BOOL matched=0;BYTE uuid[16];
 for(DWORD i=0;i<header[4];i++){
  DWORD cmd[2];if(offset>limit||limit-offset<8||!rd(base+offset,cmd,8)||cmd[1]<8||cmd[1]>limit-offset)break;
  if(cmd[0]==0x1b&&cmd[1]==24){matched=rd(base+offset+8,uuid,16)&&!memcmp(uuid,expected_uuid,16);break;}
  offset+=cmd[1];
 }
 static const BYTE expected[]={0x39,0x53,0x7c,0xb8,0,0,0,0,0x90,0x90,0x90,0x01,0xd0,0x89,0x43,0x7c,0x89,0xf1,0xe9,0xcc,0xfe,0xff,0xff};
 BYTE actual[sizeof expected];BOOL code=rd(base+0x50fd,actual,sizeof actual)&&!memcmp(actual,expected,sizeof actual);
 value("AUDIO_NATIVE_BASE=",base);value("AUDIO_NATIVE_UUID_MATCH=",matched);value("AUDIO_NATIVE_FIXED_CODE_MATCH=",code);
 line(matched&&code?"AUDIO_NATIVE_FIXED_IMPLEMENTATION_VERIFIED: not proof of gameplay or crash resolution":"AUDIO_NATIVE_IMPLEMENTATION_MISMATCH: do not claim fixed driver is active");
 R.audio_observed=1;
}

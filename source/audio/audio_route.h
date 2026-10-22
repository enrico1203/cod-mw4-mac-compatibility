/* Select the isolated sp26coreaudio.so before mmdevapi initializes a driver.
 * Checks the PE architecture, actual loader reference, original string and
 * zero driver table. Only the target process's eight string bytes change.
 * Caller must own an inactive target or hold its debug load event.
 */
static int audio_route_read(HANDLE process,QWORD at,void*out,SIZE_T n){SIZE_T got=0;return ReadProcessMemory(process,(void*)(uintptr_t)at,out,n,&got)&&got==n;}
static int audio_route_equal(const BYTE*a,const BYTE*b,SIZE_T n){for(SIZE_T i=0;i<n;i++)if(a[i]!=b[i])return 0;return 1;}
static int audio_route_apply(HANDLE process,QWORD base){
 DWORD pe=0,signature=0,size=0;WORD machine=0,magic=0;QWORD table=1;
 if(base>UINT64_MAX-0x2d000||!audio_route_read(process,base+0x3c,&pe,4)||pe>4096)return 1;
 if(!audio_route_read(process,base+pe,&signature,4)||signature!=0x4550||
    !audio_route_read(process,base+pe+4,&machine,2)||machine!=0x8664||
    !audio_route_read(process,base+pe+24,&magic,2)||magic!=0x20b||
    !audio_route_read(process,base+pe+24+56,&size,4)||size<0x28050||size>0x40000000)return 2;
 static const BYTE reference[]={0x48,0x8d,0x05,0xbd,0xc3,0,0};BYTE bytes[10];
 if(!audio_route_read(process,base+0x12a0a,bytes,7)||!audio_route_equal(bytes,reference,7))return 3;
 static const BYTE original[]={'w',0,'i',0,'n',0,'e',0,0,0};
 static const BYTE replacement[]={'s',0,'p',0,'2',0,'6',0};
 if(!audio_route_read(process,base+0x1edce,bytes,10)||!audio_route_equal(bytes,original,10))return 4;
 if(!audio_route_read(process,base+0x28048,&table,8)||table)return 5;
 void*site=(void*)(uintptr_t)(base+0x1edce);DWORD old=0,discard=0;SIZE_T written=0;
 if(!VirtualProtectEx(process,site,8,0x40,&old))return 6;
 int wrote=WriteProcessMemory(process,site,replacement,8,&written)&&written==8;
 int flushed=FlushInstructionCache(process,site,8);
 int restored=VirtualProtectEx(process,site,8,old,&discard);
 if(!wrote||!flushed||!restored)return 7;
 if(!audio_route_read(process,base+0x1edce,bytes,8)||!audio_route_equal(bytes,replacement,8))return 8;
 return 0;
}

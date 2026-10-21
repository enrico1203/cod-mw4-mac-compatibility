/* V4: narrowly scoped GPU timestamp conversion fallback.
 * No invented frequency; no change to graphics DLLs, driver state or APIs.
 * If the existing microsecond scale is nonzero, resume the exact old code.
 * If zero, return unavailable (AL=1) with zero outputs instead of dividing.
 * One known caller treats AL=1 as an incomplete measurement. Two other
 * direct call sites ignore AL and will see zero durations. This is a
 * compatibility fallback, NOT a claim that GPU timing is implemented.
 *
 * Leaf trampoline: no calls, no stack adjustment, no nonvolatile register
 * changes. The counter is in a separately allocated RW (not executable)
 * page. Code is placed ONLY into a checked 73-byte CC cave that V4 EXE
 * normalization already restores. The old frequency load is replaced last.
 */
#include "gpu_timer_signatures.h"
#define GPU_TIMER_STUB_BYTES 44u
#define GPU_TIMER_PATCH_BYTES 7u

typedef struct {
 BOOL installed,observed,warning,hit_notice;
 QWORD counter,last_count,last_scale;
 BYTE stub[GPU_TIMER_STUB_BYTES],jump[GPU_TIMER_PATCH_BYTES];
} GpuTimerFix;
static GpuTimerFix GPU;

static int timer_rel32(BYTE *dst,QWORD destination,QWORD next){
 if(destination>=next){QWORD d=destination-next;if(d>0x7fffffffull)return 0;put32(dst,(DWORD)d);}
 else{QWORD d=next-destination;if(d>0x80000000ull)return 0;put32(dst,(DWORD)(0u-(DWORD)d));}
 return 1;
}
static int timer_emit(QWORD base,QWORD counter,BYTE stub[GPU_TIMER_STUB_BYTES],BYTE jump[GPU_TIMER_PATCH_BYTES]){
 /* mov r11,[rip+scale]; test r11,r11; jnz original+7
  * movabs r11,counter; lock inc qword[r11]
  * xor eax,eax; mov [r10],rax; mov [r8],rax; mov eax,1; ret */
 static const BYTE template_code[GPU_TIMER_STUB_BYTES]={
  0x4c,0x8b,0x1d,0,0,0,0, 0x4d,0x85,0xdb, 0x0f,0x85,0,0,0,0,
  0x49,0xbb,0,0,0,0,0,0,0,0, 0xf0,0x49,0xff,0x03,
  0x31,0xc0, 0x49,0x89,0x02, 0x49,0x89,0x00,
  0xb8,0x01,0,0,0,0xc3
 };
 if(!counter||base>UINT64_MAX-GPU_TIMER_SCALE_RVA-8u)return 0;
 QWORD cave=base+GPU_TIMER_CAVE_RVA,load=base+GPU_TIMER_LOAD_RVA;
 memcpy(stub,template_code,sizeof template_code);jump[0]=0xe9;jump[5]=jump[6]=0x90;
 if(!timer_rel32(stub+3,base+GPU_TIMER_SCALE_RVA,cave+7)||
    !timer_rel32(stub+12,load+7,cave+16)||!timer_rel32(jump+1,cave,load+5))return 0;
 put64(stub+18,counter);return 1;
}
static int timer_signature(DWORD rva,const BYTE*expected,SIZE_T n){
 BYTE data[160];if(n>sizeof data||!rd(R.base+rva,data,n)||memcmp(data,expected,n)){
  value("GPU_TIMER_IDENTITY_MISMATCH_RVA=",rva);return 0;
 }return 1;
}
static int gpu_timer_install(void){
 if(R.probe)return 1; /* The existing probe tests transport, not this game-specific patch. */
 if(GPU.installed){line("ERROR GPU timer guard installed twice");return 0;}
 if(!timer_signature(GPU_TIMER_READ_RVA,gpu_timer_read_signature,sizeof gpu_timer_read_signature)||
    !timer_signature(GPU_TIMER_INIT_RVA,gpu_timer_init_signature,sizeof gpu_timer_init_signature)||
    !timer_signature(GPU_TIMER_CALLER_RVA,gpu_timer_caller_signature,sizeof gpu_timer_caller_signature))return 0;
 BYTE cave[GPU_TIMER_CAVE_BYTES];if(!rd(R.base+GPU_TIMER_CAVE_RVA,cave,sizeof cave))return 0;
 for(unsigned i=0;i<sizeof cave;i++)if(cave[i]!=0xcc){line("ERROR GPU timer code cave is not original CC padding");return 0;}
 /* The game is still held at the initial gate. Refuse on any discrepancy. */
 void *counter=VirtualAllocEx(R.p,0,4096,0x3000,0x04);
 if(!counter){err("VirtualAllocEx GPU timer counter");return 0;}
 GPU.counter=(QWORD)(uintptr_t)counter;
 QWORD zero=1;if(!rd(GPU.counter,&zero,sizeof zero)||zero){line("ERROR GPU timer counter allocation was not zeroed");return 0;}
 MBI data;if(VirtualQueryEx(R.p,counter,&data,sizeof data)!=sizeof data||data.state!=0x1000u||data.protect!=0x04u){line("ERROR GPU timer counter must be committed read/write, non-executable");return 0;}
 if(!timer_emit(R.base,GPU.counter,GPU.stub,GPU.jump))return 0;
 if(!wr(R.base+GPU_TIMER_CAVE_RVA,GPU.stub,sizeof GPU.stub)||
    !wr(R.base+GPU_TIMER_LOAD_RVA,GPU.jump,sizeof GPU.jump))return 0;
 GPU.installed=1;
 value("GPU_TIMER_GUARD_INSTALLED_RVA=",GPU_TIMER_LOAD_RVA);
 value("GPU_TIMER_GUARD_CAVE_RVA=",GPU_TIMER_CAVE_RVA);
 value("GPU_TIMER_SCALE_ADDRESS=",R.base+GPU_TIMER_SCALE_RVA);
 value("GPU_TIMER_COUNTER_ADDRESS=",GPU.counter);
 line("GPU_TIMER_POLICY: zero scale -> unavailable sample (AL=1), both outputs zero; nonzero -> unchanged original conversion");
 line("GPU_TIMER_LIMIT: raw GetTimestampFrequency result/HRESULT not observed; sampled slot may precede normalization; fallback is not a GPU timing implementation");
 return 1;
}
static int gpu_timer_verify(void){
 if(R.probe)return 1;
 if(!GPU.installed){line("ERROR GPU timer guard was not installed");return 0;}
 return timer_signature(GPU_TIMER_LOAD_RVA,GPU.jump,sizeof GPU.jump)&&
        timer_signature(GPU_TIMER_CAVE_RVA,GPU.stub,sizeof GPU.stub);
}
static void observe_gpu_timer(QWORD elapsed){
 if(!GPU.installed||R.probe)return;
 QWORD count=0,scale=0;
 if(!rd(GPU.counter,&count,sizeof count)||!rd(R.base+GPU_TIMER_SCALE_RVA,&scale,sizeof scale)){
  if(!GPU.warning){line("GPU_TIMER_OBSERVATION_UNAVAILABLE: read-only sample failed; game not stopped");GPU.warning=1;}return;
 }
 if(!GPU.observed||count!=GPU.last_count||scale!=GPU.last_scale){
  value("GPU_TIMER_OBSERVED_ELAPSED_MS=",elapsed);
  value("GPU_TIMER_DIVISOR_SLOT_VALUE=",scale);value("GPU_TIMER_ZERO_SCALE_SAMPLES=",count);
  GPU.observed=1;GPU.last_count=count;GPU.last_scale=scale;
 }
 if(count&&!GPU.hit_notice){GPU.hit_notice=1;line("GPU_TIMER_ZERO_SCALE_PATH_OBSERVED: conversion fallback actually executed; not proof of rendering/gameplay");}
}

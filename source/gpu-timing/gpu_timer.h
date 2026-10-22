/* Isolated trial: raw-frequency microseconds with original zero fallback,
 * quotient overflow fallback and failed-HRESULT invalidation. The existing
 * 44-byte guard is unchanged. Journal code is RX; all counters are separate RW.
 * Existing init arithmetic/volatile registers/flags are preserved, while its
 * normalization store is replaced by a detour returning after that store. */
#include "gpu_timer_signatures.h"
#define GPU_TIMER_STUB_BYTES 44u
#define GPU_TIMER_PATCH_BYTES 7u

typedef struct {
 BOOL installed,observed,warning,hit_notice;
 QWORD counter,last_count,last_scale;
 BYTE stub[GPU_TIMER_STUB_BYTES],jump[GPU_TIMER_PATCH_BYTES];
 BYTE body[71],init[28],journal[54];QWORD journal_address,last_calls,last_conversions,last_hr;
} GpuTimerFix;
static GpuTimerFix GPU;


#include "gpu_timer_emit.h"
static int timer_signature(DWORD rva,const BYTE*expected,SIZE_T n){
 BYTE actual[160];return n<=sizeof actual&&rd(R.base+rva,actual,n)&&!memcmp(actual,expected,n);
}
static QWORD timer_near_page(void){
 for(unsigned i=1;i<=64;i++){
  QWORD distance=(QWORD)i*65536u;if(R.base<distance)break;
  void*wanted=(void*)(uintptr_t)(R.base-distance);void*p=VirtualAllocEx(R.p,wanted,4096,0x3000,0x04);
  if(p){if(p!=wanted){line("ERROR GPU timing allocation did not honor requested free address");return 0;}return(QWORD)(uintptr_t)p;}
 }
 line("ERROR Could not allocate a nearby private GPU timing page");return 0;
}
static int gpu_timer_install(void){
 if(R.probe)return 1;
 if(GPU.installed)return 0;
 if(!timer_signature(GPU_TIMER_READ_RVA,gpu_timer_read_signature,sizeof gpu_timer_read_signature)||
    !timer_signature(GPU_TIMER_INIT_RVA,gpu_timer_init_signature,sizeof gpu_timer_init_signature)||
    !timer_signature(GPU_TIMER_CALLER_RVA,gpu_timer_caller_signature,sizeof gpu_timer_caller_signature)){
  line("ERROR GPU timing operation instructions differ");return 0;
 }
 BYTE cave[GPU_TIMER_CAVE_BYTES];if(!rd(R.base+GPU_TIMER_CAVE_RVA,cave,sizeof cave))return 0;
 for(unsigned i=0;i<sizeof cave;i++)if(cave[i]!=0xcc)return 0;
 GPU.counter=timer_near_page();GPU.journal_address=timer_near_page();
 if(!GPU.counter||!GPU.journal_address||GPU.counter==GPU.journal_address)return 0;
 QWORD initial[3]={1,1,1};if(!rd(GPU.counter,initial,sizeof initial)||initial[0]||initial[1]||initial[2])return 0;
 DWORD pending=0x7fffffff;if(!wr(GPU.counter+8,&pending,4))return 0;
 if(!timer_emit(R.base,GPU.counter,GPU.stub,GPU.jump)||
    !timer_raw_emit(R.base,GPU.counter,GPU.journal_address,GPU.body,GPU.init,GPU.journal))return 0;
 if(!wr(GPU.journal_address,GPU.journal,sizeof GPU.journal))return 0;
 DWORD old_protect=0;if(!VirtualProtectEx(R.p,(void*)(uintptr_t)GPU.journal_address,4096,0x20,&old_protect))return 0;
 MBI code,data;
 if(VirtualQueryEx(R.p,(void*)(uintptr_t)GPU.journal_address,&code,sizeof code)!=sizeof code||code.protect!=0x20||
    VirtualQueryEx(R.p,(void*)(uintptr_t)GPU.counter,&data,sizeof data)!=sizeof data||data.protect!=0x04)return 0;
 if(!wr(R.base+GPU_TIMER_CAVE_RVA,GPU.stub,sizeof GPU.stub)||
    !wr(R.base+GPU_TIMING_BODY_RVA,GPU.body,64)||
    !wr(R.base+GPU_TIMING_BODY_RVA+64,GPU.body+64,7)||
    !wr(R.base+GPU_TIMING_INIT_TAIL_RVA,GPU.init,sizeof GPU.init)||
    !wr(R.base+GPU_TIMER_LOAD_RVA,GPU.jump,sizeof GPU.jump))return 0;
 GPU.installed=1;line("GPU_TIMER_POLICY: invalid -> unavailable (AL=1), zero outputs; raw frequency conversion otherwise");
 line("GPU_RAW_TIMING_READY");return 1;
}
static int gpu_timer_verify(void){
 if(R.probe)return 1;
 BYTE code[54];return GPU.installed&&
  timer_signature(GPU_TIMER_LOAD_RVA,GPU.jump,sizeof GPU.jump)&&
  timer_signature(GPU_TIMER_CAVE_RVA,GPU.stub,sizeof GPU.stub)&&
  timer_signature(GPU_TIMING_BODY_RVA,GPU.body,sizeof GPU.body)&&
  timer_signature(GPU_TIMING_INIT_TAIL_RVA,GPU.init,sizeof GPU.init)&&
  rd(GPU.journal_address,code,sizeof code)&&!memcmp(code,GPU.journal,sizeof code);
}
static void observe_gpu_timer(QWORD elapsed){
 if(!GPU.installed||R.probe)return;
 QWORD data[3]={0},raw=0;if(!rd(GPU.counter,data,sizeof data)||!rd(R.base+GPU_TIMER_SCALE_RVA,&raw,8))return;
 DWORD hr=(DWORD)data[1],calls=(DWORD)(data[1]>>32);
 if(!GPU.observed||raw!=GPU.last_scale||hr!=GPU.last_hr||calls!=GPU.last_calls||data[0]!=GPU.last_count||data[2]!=GPU.last_conversions){
  value("GPU_TIMING_ELAPSED_MS=",elapsed);value("GPU_RAW_FREQUENCY=",raw);value("GPU_RAW_LAST_HRESULT=",hr);value("GPU_RAW_INIT_CALLS=",calls);
  value("GPU_TIMING_INVALID_CONVERSIONS=",data[0]);value("GPU_TIMING_COMPLETED_CONVERSIONS=",data[2]);
  GPU.observed=1;GPU.last_scale=raw;GPU.last_hr=hr;GPU.last_calls=calls;GPU.last_count=data[0];GPU.last_conversions=data[2];
 }
}

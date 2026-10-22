#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint64_t QWORD;typedef uint32_t DWORD;typedef int BOOL;
#include "startup_wait.h"
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"policy check failed at line %d\n",__LINE__);return 1;}}while(0)
int main(void){unsigned checks=0;
 StartupWait s={0};
 CHECK(startup_wait_update(&s,20000,0,1,1,1,1,0,0,0,0,0)==STARTUP_WAIT);
 CHECK(startup_wait_update(&s,20001,0,1,1,1,1,0,0,0,0,0)==STARTUP_HARD_TIMEOUT);
 for(unsigned mask=0;mask<128;mask++){
  int ready=mask&1,h0=mask&2,h1=mask&4,pending=mask&8,armed0=mask&16,armed1=mask&32,held=mask&64;
  s=(StartupWait){0};int safe=ready&&h0&&h1&&!pending&&!armed0&&!armed1&&!held;
  int result=startup_wait_update(&s,240001,0,0,ready,h0,h1,pending,armed0,armed1,held,0);
  CHECK(result==(safe?STARTUP_ENTER_AUDIO_WAIT:STARTUP_HARD_TIMEOUT));
  if(!safe)CHECK(!s.late);
 }
 s=(StartupWait){0};CHECK(startup_wait_update(&s,6000,0,0,1,1,1,0,0,0,0,0)==STARTUP_ENTER_AUDIO_WAIT);
 CHECK(s.since==6000);
 /* This launch is already over the previous global deadline; it gets the whole late stage. */
 CHECK(startup_wait_update(&s,240001,0,0,1,1,1,0,0,0,0,0)==STARTUP_AUDIO_STATUS);
 CHECK(startup_wait_update(&s,246000,0,0,1,1,1,0,0,0,0,0)==STARTUP_WAIT);
 CHECK(startup_wait_update(&s,246001,0,0,1,1,1,0,0,0,0,0)==STARTUP_AUDIO_DECISION);
 /* Time spent deciding is excluded only when the human chooses Retry. */
 startup_wait_retry(&s,500000);
 CHECK(startup_wait_update(&s,500001,0,0,1,1,1,0,0,0,0,0)==STARTUP_WAIT);
 CHECK(startup_wait_update(&s,740000,0,0,1,1,1,0,0,0,0,0)==STARTUP_AUDIO_STATUS);
 CHECK(startup_wait_update(&s,740001,0,0,1,1,1,0,0,0,0,0)==STARTUP_AUDIO_DECISION);
 CHECK(startup_wait_update(&s,999999,0,0,1,1,1,0,0,0,0,1)==STARTUP_WAIT);
 /* No retries through an armed breakpoint/pending step/owned suspend. */
 CHECK(startup_wait_update(&s,500001,0,0,1,1,1,1,0,0,0,0)==STARTUP_HARD_TIMEOUT);
 CHECK(startup_wait_update(&s,500001,0,0,1,1,1,0,1,0,0,0)==STARTUP_HARD_TIMEOUT);
 CHECK(startup_wait_update(&s,500001,0,0,1,1,1,0,0,1,0,0)==STARTUP_HARD_TIMEOUT);
 CHECK(startup_wait_update(&s,500001,0,0,1,1,1,0,0,0,1,0)==STARTUP_HARD_TIMEOUT);
 /* A reversed clock cannot turn unsigned subtraction into a false expiry. */
 CHECK(startup_wait_update(&s,100,0,0,1,1,1,0,0,0,0,0)==STARTUP_WAIT);CHECK(s.since==100);
 /* Exhaustive millisecond timing around early and late boundaries. */
 for(unsigned t=0;t<300100;t++){
  s=(StartupWait){1,6000,999999};
  int r=startup_wait_update(&s,t,0,0,1,1,1,0,0,0,0,0);
  CHECK(r==(t>246000?STARTUP_AUDIO_DECISION:STARTUP_WAIT));
 }
 printf("STARTUP_WAIT_POLICY_PASSED checks=%u; required-hook/probe deadlines unchanged; safe late stage; full late budget; explicit Retry reset; no bypass of pending/armed/owned-suspend; clock reversal. Model only, no game.\n",checks);return 0;
}

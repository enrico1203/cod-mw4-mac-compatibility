/* Separate required-hook deadline from the later audio-module wait.
 * A late wait never grants handoff, skips a patch or declares rendering success.
 * No CPU/thread-activity heuristic: activity is not proof of useful progress. */
#ifndef STARTUP_AUDIO_WAIT_MS
#define STARTUP_AUDIO_WAIT_MS 240000u
#endif
typedef struct {int late;QWORD since,next_notice;} StartupWait;
enum {STARTUP_WAIT=0,STARTUP_HARD_TIMEOUT=1,STARTUP_ENTER_AUDIO_WAIT=2,STARTUP_AUDIO_STATUS=3,STARTUP_AUDIO_DECISION=4};
static int startup_wait_update(StartupWait*w,QWORD now,QWORD started,BOOL probe,BOOL ready,BOOL hook0,BOOL hook1,DWORD pending,BOOL armed0,BOOL armed1,unsigned held,BOOL audio){
 if(probe)return now>=started&&now-started>20000u?STARTUP_HARD_TIMEOUT:STARTUP_WAIT;
 BOOL late_safe=ready&&hook0&&hook1&&!pending&&!armed0&&!armed1&&!held;
 if(!late_safe)return now>=started&&now-started>240000u?STARTUP_HARD_TIMEOUT:STARTUP_WAIT;
 if(audio)return STARTUP_WAIT;
 if(!w->late){w->late=1;w->since=now;w->next_notice=now+30000u;return STARTUP_ENTER_AUDIO_WAIT;}
 if(now<w->since){w->since=now;w->next_notice=now+30000u;return STARTUP_WAIT;}
 if(now-w->since>STARTUP_AUDIO_WAIT_MS)return STARTUP_AUDIO_DECISION;
 if(now>=w->next_notice){w->next_notice=now+30000u;return STARTUP_AUDIO_STATUS;}
 return STARTUP_WAIT;
}
static void startup_wait_retry(StartupWait*w,QWORD now){w->since=now;w->next_notice=now+30000u;}

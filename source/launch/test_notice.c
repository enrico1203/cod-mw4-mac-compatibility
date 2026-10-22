/* Host contract tests. These mocks are not Wine/UI integration evidence. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint8_t BYTE;typedef uint16_t WORD,WCHAR;typedef uint32_t DWORD;typedef int BOOL;typedef void*HANDLE;
#define IMP
#define W(s) ((const WCHAR*)L##s)
HANDLE GetModuleHandleW(const WCHAR*);
#include "startup_notice.h"
static unsigned checks,created,destroyed,peeked,dispatched,queued,indexed;
static BOOL fail_create;
static StartupMessage queue[100];
static HANDLE window=(HANDLE)(uintptr_t)0x1234;
#define CHECK(x) do{assert(x);checks++;}while(0)
HANDLE GetModuleHandleW(const WCHAR*s){(void)s;return (HANDLE)(uintptr_t)1;}
HANDLE CreateDialogIndirectParamW(HANDLE module,const void*data,HANDLE owner,StartupDialogProc proc,intptr_t param){
 CHECK(module!=0&&data!=0&&owner==0&&proc==startup_notice_proc&&param==0);created++;return fail_create?0:window;
}
BOOL DestroyWindow(HANDLE h){CHECK(h==window);destroyed++;return 1;}
BOOL PeekMessageW(StartupMessage*m,HANDLE h,DWORD lo,DWORD hi,DWORD mode){
 CHECK(h==0&&lo==0&&hi==0&&mode==1);peeked++;
 if(indexed==queued)return 0;*m=queue[indexed++];return 1;
}
BOOL IsDialogMessageW(HANDLE h,StartupMessage*m){CHECK(h==window);return (BOOL)startup_notice_proc(h,m->message,m->wparam,m->lparam);}
BOOL TranslateMessage(const StartupMessage*m){CHECK(m!=0);return 1;}
intptr_t DispatchMessageW(const StartupMessage*m){CHECK(m!=0);dispatched++;return 0;}
static void reset_queue(void){queued=indexed=0;}
static void push(DWORD message,uintptr_t wp){CHECK(queued<100);queue[queued++]=(StartupMessage){window,message,wp,0,0,0,0};}
static WORD word(const BYTE*b,unsigned*n,unsigned size){CHECK(*n+2<=size);WORD v=(WORD)(b[*n]|(b[*n+1]<<8));*n+=2;return v;}
static DWORD dword(const BYTE*b,unsigned*n,unsigned size){DWORD a=word(b,n,size),c=word(b,n,size);return a|(c<<16);}
static void text(const BYTE*b,unsigned*n,unsigned size,const WCHAR*expected){WORD c;do{c=word(b,n,size);CHECK(c==*expected++);}while(c);}
int main(void){
 BYTE buf[1056],good[1024];unsigned size=startup_notice_template(good,sizeof good);CHECK(size>300&&size<1024);
 for(unsigned capacity=0;capacity<=1024;capacity++){
  memset(buf,0xa5,sizeof buf);unsigned actual=startup_notice_template(buf+16,capacity);
  CHECK(actual==(capacity>=size?size:0));
  for(unsigned i=0;i<16;i++)CHECK(buf[i]==0xa5);
  for(unsigned i=16+capacity;i<sizeof buf;i++)CHECK(buf[i]==0xa5);
  if(actual)CHECK(memcmp(buf+16,good,size)==0);
 }
 unsigned n=0;CHECK(dword(good,&n,size)==0x90c808c0u);CHECK(dword(good,&n,size)==0);CHECK(word(good,&n,size)==3);
 CHECK(word(good,&n,size)==0&&word(good,&n,size)==0);CHECK(word(good,&n,size)==298&&word(good,&n,size)==96);
 CHECK(word(good,&n,size)==0&&word(good,&n,size)==0);text(good,&n,size,W("COD: MW4 Mac Compatibility"));CHECK(word(good,&n,size)==9);text(good,&n,size,W("Segoe UI"));
 const DWORD styles[]={0x50000000u,0x50010001u,0x50010000u};const WORD ids[]={0xffff,4,2};const WCHAR*titles[]={W("Initialization is taking longer than expected.\nThe game will keep starting while this window is open."),W("Keep waiting"),W("Cancel launch")};
 for(unsigned i=0;i<3;i++){
  n=(n+3)&~3u;CHECK(dword(good,&n,size)==styles[i]);CHECK(dword(good,&n,size)==0);
  WORD x=word(good,&n,size),y=word(good,&n,size),w=word(good,&n,size),h=word(good,&n,size);CHECK(x+w<=298&&y+h<=96);
  CHECK(word(good,&n,size)==ids[i]);CHECK(word(good,&n,size)==0xffff);CHECK(word(good,&n,size)==(i?0x80:0x82));text(good,&n,size,titles[i]);CHECK(word(good,&n,size)==0);
 }CHECK(n==size);
 fail_create=1;CHECK(!startup_notice_open()&&!startup_notice_window);fail_create=0;CHECK(startup_notice_open());unsigned old_created=created;CHECK(startup_notice_open()&&created==old_created);
 for(unsigned i=0;i<100;i++)push(0x400,0);
 unsigned old_peek=peeked;CHECK(startup_notice_poll()==0&&startup_notice_window==window&&indexed==32&&peeked-old_peek==32);CHECK(startup_notice_poll()==0&&indexed==64);CHECK(startup_notice_poll()==0&&indexed==96);CHECK(startup_notice_poll()==0&&indexed==100);CHECK(dispatched==100);
 reset_queue();push(0x111,4);CHECK(startup_notice_poll()==4&&!startup_notice_window);CHECK(startup_notice_poll()==0);
 CHECK(startup_notice_open());reset_queue();push(0x111,2);CHECK(startup_notice_poll()==2&&!startup_notice_window);
 CHECK(startup_notice_open());reset_queue();push(0x10,0);CHECK(startup_notice_poll()==2&&!startup_notice_window);
 CHECK(startup_notice_open());reset_queue();push(0x12,0);CHECK(startup_notice_poll()==2&&!startup_notice_window);
 CHECK(startup_notice_open());reset_queue();startup_notice_close();CHECK(!startup_notice_window&&startup_notice_poll()==0);
 CHECK(destroyed==5);CHECK(startup_notice_proc(window,0x110,0,0)==1);CHECK(startup_notice_proc(window,0x111,99,0)==0);
 printf("STARTUP_NOTICE_HOST_CONTRACT_CHECKS_PASSED=%u\n",checks);
 puts("Scope: template bounds/alignment/UTF16/control geometry, queue fairness, retry/cancel/X/quit callbacks, creation failure and automatic close; mocks only, no Wine/game/UI success claim.");
 return 0;
}

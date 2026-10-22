/* A modeless notice keeps the debugger loop running while the user decides.
 * No worker thread, no target messages, and no implicit game handoff. */
typedef struct {HANDLE window;DWORD message;uintptr_t wparam;intptr_t lparam;DWORD time;int x,y;} StartupMessage;
_Static_assert(sizeof(StartupMessage)==48 && offsetof(StartupMessage,wparam)==16,"MSG x64 ABI");
typedef intptr_t (*StartupDialogProc)(HANDLE,DWORD,uintptr_t,intptr_t);
IMP HANDLE CreateDialogIndirectParamW(HANDLE,const void*,HANDLE,StartupDialogProc,intptr_t);
IMP BOOL DestroyWindow(HANDLE);
IMP BOOL PeekMessageW(StartupMessage*,HANDLE,DWORD,DWORD,DWORD);
IMP BOOL TranslateMessage(const StartupMessage*);
IMP intptr_t DispatchMessageW(const StartupMessage*);
IMP BOOL IsDialogMessageW(HANDLE,StartupMessage*);

static HANDLE startup_notice_window;
static int startup_notice_answer;
static void startup_notice_close(void){
 if(startup_notice_window&&DestroyWindow(startup_notice_window))startup_notice_window=0;
}
static intptr_t startup_notice_proc(HANDLE window,DWORD message,uintptr_t wparam,intptr_t lparam){
 (void)lparam;
 if(message==0x110)return 1; /* WM_INITDIALOG */
 if(message==0x111&&((wparam&0xffffu)==4||(wparam&0xffffu)==2)){
  startup_notice_answer=(int)(wparam&0xffffu);DestroyWindow(window);startup_notice_window=0;return 1;
 }
 if(message==0x10){startup_notice_answer=2;DestroyWindow(window);startup_notice_window=0;return 1;}
 return 0;
}

typedef struct {BYTE*bytes;unsigned used,capacity;BOOL good;} StartupTemplate;
static void startup_template_word(StartupTemplate*t,WORD v){
 if(!t->good||t->capacity-t->used<2){t->good=0;return;}
 t->bytes[t->used++]=(BYTE)v;t->bytes[t->used++]=(BYTE)(v>>8);
}
static void startup_template_dword(StartupTemplate*t,DWORD v){startup_template_word(t,(WORD)v);startup_template_word(t,(WORD)(v>>16));}
static void startup_template_text(StartupTemplate*t,const WCHAR*s){do{startup_template_word(t,*s);}while(*s++);}
static void startup_template_item(StartupTemplate*t,DWORD style,WORD x,WORD y,WORD width,WORD height,WORD id,WORD cls,const WCHAR*text){
 if(t->used&3u)startup_template_word(t,0);
 startup_template_dword(t,style);startup_template_dword(t,0);
 startup_template_word(t,x);startup_template_word(t,y);startup_template_word(t,width);startup_template_word(t,height);startup_template_word(t,id);
 startup_template_word(t,0xffff);startup_template_word(t,cls);startup_template_text(t,text);startup_template_word(t,0);
}
static unsigned startup_notice_template(BYTE*bytes,unsigned capacity){
 StartupTemplate t={bytes,0,capacity,1};
 startup_template_dword(&t,0x90c808c0u); /* Popup, visible, caption, system menu, font, centered. */
 startup_template_dword(&t,0);startup_template_word(&t,3);
 startup_template_word(&t,0);startup_template_word(&t,0);startup_template_word(&t,298);startup_template_word(&t,96);
 startup_template_word(&t,0);startup_template_word(&t,0);
 startup_template_text(&t,W("COD: MW4 Mac Compatibility"));
 startup_template_word(&t,9);startup_template_text(&t,W("Segoe UI"));
 startup_template_item(&t,0x50000000u,12,10,274,45,0xffff,0x82,W("Initialization is taking longer than expected.\nThe game will keep starting while this window is open."));
 startup_template_item(&t,0x50010001u,106,65,86,23,4,0x80,W("Keep waiting"));
 startup_template_item(&t,0x50010000u,200,65,86,23,2,0x80,W("Cancel launch"));
 return t.good?t.used:0;
}
static BOOL startup_notice_open(void){
 static __declspec(align(4)) BYTE bytes[1024];
 if(startup_notice_window)return 1;
 if(!startup_notice_template(bytes,sizeof bytes))return 0;
 startup_notice_answer=0;
 startup_notice_window=CreateDialogIndirectParamW(GetModuleHandleW(0),bytes,0,startup_notice_proc,0);
 return startup_notice_window!=0;
}
static int startup_notice_poll(void){
 if(startup_notice_window){
  StartupMessage message;
  /* A busy UI queue must not starve debug events. */
  for(unsigned count=0;count<32&&PeekMessageW(&message,0,0,0,1);count++){
   if(message.message==0x12){startup_notice_answer=2;startup_notice_close();break;}
   if(!startup_notice_window||!IsDialogMessageW(startup_notice_window,&message)){TranslateMessage(&message);DispatchMessageW(&message);}
  }
 }
 int answer=startup_notice_answer;startup_notice_answer=0;return answer;
}

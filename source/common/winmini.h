#ifndef WINMINI_H
#define WINMINI_H
/* Minimal Windows x64 ABI declarations. No SDK, CRT, or third-party runtime. */
#include <stdint.h>
#include <stddef.h>
typedef uint8_t BYTE; typedef uint16_t WORD; typedef uint32_t DWORD; typedef int32_t BOOL; typedef uint64_t QWORD; typedef uint16_t WCHAR; typedef void *HANDLE; typedef size_t SIZE_T;
#define W(s) ((const WCHAR *)L##s)
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#define IMP __declspec(dllimport)
#define COUNT(a) (sizeof(a)/sizeof((a)[0]))
typedef struct {DWORD cb; WCHAR *reserved,*desktop,*title;DWORD x,y,xsize,ysize,xc,yc,fill,flags;WORD show,reserved2;BYTE *reserved3;HANDLE in,out,err;} STARTUPINFOW;
typedef struct {HANDLE process,thread;DWORD pid,tid;} PROCESS_INFORMATION;
typedef struct {DWORD code,flags;void *record,*address;DWORD count;QWORD info[15];} EX_RECORD;
typedef struct {QWORD homes[6];DWORD ContextFlags,MxCsr;WORD cs,ds,es,fs,gs,ss;DWORD EFlags;QWORD Dr0,Dr1,Dr2,Dr3,Dr6,Dr7;QWORD Rax,Rcx,Rdx,Rbx,Rsp,Rbp,Rsi,Rdi,R8,R9,R10,R11,R12,R13,R14,R15,Rip;BYTE floating[512],vectors[416];QWORD VectorControl,DebugControl,LastBranchToRip,LastBranchFromRip,LastExceptionToRip,LastExceptionFromRip;} __declspec(align(16)) CONTEXT;
typedef struct {DWORD code,pid,tid;union {struct {EX_RECORD record;DWORD first;} exception;struct {HANDLE file,process,thread;void *base;DWORD offset,size;void *tls,*start,*name;WORD unicode;} create;struct {HANDLE thread;void *tls,*start;} thread;struct {DWORD code;} exit;struct {HANDLE file;void *base;DWORD offset,size;void *name;WORD unicode;} dll;struct {void *base;} unload;struct {void *data;WORD unicode,length;} text;BYTE padding[160];} u;} DEBUG_EVENT;
_Static_assert(sizeof(void*)==8,"x64 only");
_Static_assert(sizeof(STARTUPINFOW)==104,"STARTUPINFO ABI");
_Static_assert(sizeof(DEBUG_EVENT)==176 && offsetof(DEBUG_EVENT,u)==16,"DEBUG_EVENT ABI");
_Static_assert(sizeof(CONTEXT)==1232 && offsetof(CONTEXT,Rip)==248 && offsetof(CONTEXT,EFlags)==68,"CONTEXT ABI");
IMP BOOL CreateProcessW(const WCHAR*,WCHAR*,void*,void*,BOOL,DWORD,void*,const WCHAR*,STARTUPINFOW*,PROCESS_INFORMATION*);
IMP BOOL WaitForDebugEvent(DEBUG_EVENT*,DWORD); IMP BOOL ContinueDebugEvent(DWORD,DWORD,DWORD); IMP BOOL DebugActiveProcessStop(DWORD); IMP BOOL DebugSetProcessKillOnExit(BOOL);
typedef struct {void *base,*allocation;DWORD allocation_protect;SIZE_T region_size;DWORD state,protect,type;} MBI;
_Static_assert(sizeof(MBI)==48 && offsetof(MBI,protect)==36,"MBI ABI");
IMP void *VirtualAllocEx(HANDLE,void*,SIZE_T,DWORD,DWORD);
IMP SIZE_T VirtualQueryEx(HANDLE,const void*,MBI*,SIZE_T);
IMP BOOL ReadProcessMemory(HANDLE,const void*,void*,SIZE_T,SIZE_T*); IMP BOOL WriteProcessMemory(HANDLE,void*,const void*,SIZE_T,SIZE_T*);IMP BOOL VirtualProtectEx(HANDLE,void*,SIZE_T,DWORD,DWORD*);IMP BOOL FlushInstructionCache(HANDLE,const void*,SIZE_T);
IMP BOOL GetThreadContext(HANDLE,CONTEXT*); IMP BOOL SetThreadContext(HANDLE,const CONTEXT*); IMP DWORD SuspendThread(HANDLE);IMP DWORD ResumeThread(HANDLE);IMP HANDLE OpenThread(DWORD,BOOL,DWORD);
IMP BOOL CloseHandle(HANDLE); IMP HANDLE GetCurrentProcess(void); IMP BOOL TerminateProcess(HANDLE,unsigned); IMP DWORD WaitForSingleObject(HANDLE,DWORD); IMP BOOL GetExitCodeProcess(HANDLE,DWORD*); IMP DWORD GetLastError(void);IMP QWORD GetTickCount64(void);IMP void Sleep(DWORD);
IMP HANDLE CreateFileW(const WCHAR*,DWORD,DWORD,void*,DWORD,DWORD,HANDLE);IMP BOOL ReadFile(HANDLE,void*,DWORD,DWORD*,void*);IMP BOOL WriteFile(HANDLE,const void*,DWORD,DWORD*,void*);IMP BOOL FlushFileBuffers(HANDLE);IMP BOOL GetFileSizeEx(HANDLE,int64_t*);IMP DWORD GetFileAttributesW(const WCHAR*);
IMP DWORD GetModuleFileNameW(HANDLE,WCHAR*,DWORD);IMP HANDLE GetModuleHandleW(const WCHAR*);IMP void *GetProcAddress(HANDLE,const char*);IMP DWORD GetFinalPathNameByHandleW(HANDLE,WCHAR*,DWORD,DWORD);
IMP WCHAR *GetCommandLineW(void); IMP WCHAR **CommandLineToArgvW(const WCHAR*,int*);IMP void *LocalFree(void*);IMP HANDLE GetStdHandle(DWORD); IMP void ExitProcess(unsigned);
IMP int WideCharToMultiByte(unsigned,DWORD,const WCHAR*,int,char*,int,const char*,BOOL*);IMP int MessageBoxW(HANDLE,const WCHAR*,const WCHAR*,unsigned);

/* V3: independent handle and read-only post-detach observations. */
IMP BOOL DuplicateHandle(HANDLE,HANDLE,HANDLE,HANDLE*,DWORD,BOOL,DWORD);
IMP BOOL EnumWindows(BOOL (*)(HANDLE,intptr_t),intptr_t);
IMP DWORD GetWindowThreadProcessId(HANDLE,DWORD*);
IMP BOOL IsWindowVisible(HANDLE);
typedef struct {DWORD dwSize,module_id,pid,global_uses,process_uses;BYTE *base;DWORD size;HANDLE module;WCHAR name[256],path[260];} MODULEENTRY32W;
_Static_assert(sizeof(MODULEENTRY32W)==1080 && offsetof(MODULEENTRY32W,name)==48,"MODULEENTRY32W ABI");
IMP HANDLE CreateToolhelp32Snapshot(DWORD,DWORD);
IMP BOOL Module32FirstW(HANDLE,MODULEENTRY32W*);
IMP BOOL Module32NextW(HANDLE,MODULEENTRY32W*);

#define DBG_CONTINUE 0x00010002u
#define DBG_EXCEPTION_NOT_HANDLED 0x80010001u
#define EX_BREAK 0x80000003u
#define EX_STEP 0x80000004u
#endif

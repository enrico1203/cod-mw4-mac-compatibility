#include "input_poll_bytes.h"
/* Called only after the existing holdothers succeeds at final handoff, after audio routing.
 * Replace a constant-false exit test with Sleep(1) using the existing IAT.
 * All three key tests, both actions and the loop back-edge remain unchanged.
 */
static int input_poll_install(void) {
    if(R.probe)return 1;
    if(!rex_has_legacy_input){line("INPUT_WAIT_NOT_APPLIED_TO_THIS_REX_BUILD");return 1;}
    BYTE got[sizeof input_poll_original];QWORD sleep_function=0;MBI memory;
    if(!R.rex || !rd(R.rex+0xb800,got,sizeof got) || memcmp(got,input_poll_original,sizeof got)) {
        line("WARNING Optional input wait could not be applied: the loop is different or unreadable. Continuing without it.");return 1;
    }
    if(!rd(R.rex+0x10020,&sleep_function,sizeof sleep_function)||!sleep_function||
       VirtualQueryEx(R.p,(void *)(uintptr_t)sleep_function,&memory,sizeof memory)!=sizeof memory||
       memory.state!=0x1000u||!(memory.protect&0xf0u)) {
        line("WARNING Optional input wait could not be applied: its wait function is unavailable. Continuing without it.");return 1;
    }
    /* At late handoff a polling thread may already occupy this block.
     * Validate every held thread before writing. The three original instruction
     * boundaries have no side effects beyond volatile EAX/flags; restart them
     * at the new block entry so no thread resumes in a new immediate operand.
     */
    DWORD restart[256];unsigned restart_count=0;CONTEXT context;
    for(unsigned i=0;i<R.count;++i)if(R.th[i].id) {
        memset(&context,0,sizeof context);context.ContextFlags=0x100001;
        if(!GetThreadContext(R.th[i].h,&context)){line("WARNING Optional input wait could not inspect a thread. Continuing without it.");return 1;}
        if(context.Rip>=R.rex+0xb804 && context.Rip<R.rex+0xb80f) {
            QWORD offset=context.Rip-R.rex;
            if(offset!=0xb804&&offset!=0xb806&&offset!=0xb809){line("WARNING Optional input wait cannot update an active instruction. Continuing without it.");return 1;}
            restart[restart_count++]=i;
        }
    }
    if(!wr(R.rex+0xb804,input_poll_patch,sizeof input_poll_patch))return 0;
    memcpy(got,input_poll_original,sizeof got);memcpy(got+4,input_poll_patch,sizeof input_poll_patch);
    BYTE after[sizeof got];
    if(!rd(R.rex+0xb800,after,sizeof after)||memcmp(got,after,sizeof got)) {
        line("ERROR rex input loop post-write verification");return 0;
    }
    for(unsigned n=0;n<restart_count;++n) {
        unsigned i=restart[n];memset(&context,0,sizeof context);context.ContextFlags=0x100001;
        if(!GetThreadContext(R.th[i].h,&context))return 0;
        if(context.Rip<R.rex+0xb804||context.Rip>=R.rex+0xb80f)return 0;
        context.Rip=R.rex+0xb804;
        if(!SetThreadContext(R.th[i].h,&context))return 0;
        value("INPUT_POLL_RESTARTED_BLOCK_TID=",R.th[i].id);
    }
    value("INPUT_POLL_HELD_THREADS_CHECKED=",R.count);
    value("INPUT_POLL_PATCH_RVA=",0xb804);value("INPUT_POLL_REQUESTED_WAIT_MS=",1);
    value("INPUT_POLL_SLEEP_TARGET=",sleep_function);
    line("INPUT_POLL_VERIFIED: only 11 bytes in child rex loop changed; game files and key actions unchanged");
    return 1;
}

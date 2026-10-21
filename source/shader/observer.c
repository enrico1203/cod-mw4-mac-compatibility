/* Isolated, identity-guarded D3D12 OPTIONS3 experiment. Two already-writable
 * process-local dispatch slots only; no executable/protection changes.
 * CAP_MASK=1 masks only successful exact-size BarycentricsSupported==1 to 0.
 * Early loaded via a separate ntdll copy; installed files stay unchanged. */
#include <dlfcn.h>
#include <errno.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#ifndef CAP_MASK
#define CAP_MASK 0
#endif
static bool target_image_name(const char *path) {
    if(!path) return false;
    const char *slash=strrchr(path,'/');
    return !strcmp(slash?slash+1:path,"D3DMetal");
}
#define DIRECT_SLOT 0x527f78
#define DIRECT_METHOD 0x70a32
#define UNPACK_SLOT 0x528218
#define UNPACK_METHOD 0x80d29
typedef struct {uint32_t copy_timestamps, typed_cast, write_flags, view_tier, barycentrics;} Options3;
typedef struct {void *device; uint32_t feature,padding; void *data; uint32_t size; int32_t hr;} Params;
typedef int32_t (__attribute__((ms_abi)) *Direct)(void *,uint32_t,void *,uint32_t);
typedef int32_t (*Unpack)(Params *);
_Static_assert(sizeof(Options3)==20,"OPTIONS3 ABI");
_Static_assert(sizeof(Params)==32 && offsetof(Params,data)==16 && offsetof(Params,hr)==28,"unpack ABI");
static Direct original_direct;
static Unpack original_unpack;
static _Atomic unsigned other_events,options3_events;
static void emit(const char *line,int n,size_t capacity) {
    if(n>0 && (size_t)n<capacity) (void)write(STDERR_FILENO,line,(size_t)n);
}
static void result(uint32_t feature,void *data,uint32_t size,int32_t hr,const char *route) {
    int saved_errno=errno;
    Options3 before={0},after={0};
    bool valid=feature==21 && size==sizeof(Options3) && hr==0 && data;
    if(valid) {
        memcpy(&before,data,sizeof before);
        if(CAP_MASK && before.barycentrics==1) {
            uint32_t unsupported=0;
            memcpy((char *)data+offsetof(Options3,barycentrics),&unsupported,sizeof unsupported);
        }
        memcpy(&after,data,sizeof after);
    }
    unsigned sequence=atomic_fetch_add_explicit(feature==21?&options3_events:&other_events,1,memory_order_relaxed);
    if(sequence<32) {
        struct timespec now;clock_gettime(CLOCK_REALTIME,&now);
        char line[768];
        int n=snprintf(line,sizeof line,
            "SP26_CAPABILITY {\"event\":\"query\",\"pid\":%d,\"unix_seconds\":%lld.%09ld,\"route\":\"%s\",\"feature\":%u,\"size\":%u,\"hresult\":%u,\"valid_options3\":%s,\"mask_enabled\":%s,\"barycentrics_before\":%u,\"barycentrics_after\":%u,\"other_fields\":[%u,%u,%u,%u]}\n",
            getpid(),(long long)now.tv_sec,now.tv_nsec,route,feature,size,(uint32_t)hr,
            valid?"true":"false",CAP_MASK?"true":"false",before.barycentrics,after.barycentrics,
            before.copy_timestamps,before.typed_cast,before.write_flags,before.view_tier);
        emit(line,n,sizeof line);
    }
    errno=saved_errno;
}
static int32_t __attribute__((ms_abi)) observe_direct(void *device,uint32_t feature,void *data,uint32_t size) {
    int32_t hr=original_direct(device,feature,data,size);
    result(feature,data,size,hr,"direct");return hr;
}
static int32_t observe_unpack(Params *p) {
    int32_t status=original_unpack(p);
    if(status==0) result(p->feature,p->data,p->size,p->hr,"unixcall");
    return status;
}
#ifndef CAP_CONTRACT_TEST
static bool writable(uintptr_t slot) {
    mach_vm_address_t address=slot;mach_vm_size_t size=0;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t count=VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object=MACH_PORT_NULL;
    kern_return_t kr=mach_vm_region(mach_task_self(),&address,&size,VM_REGION_BASIC_INFO_64,(vm_region_info_t)&info,&count,&object);
    if(object) mach_port_deallocate(mach_task_self(),object);
    return kr==KERN_SUCCESS && address<=slot && size>=sizeof(void *) && slot-address<=size-sizeof(void *) &&
        (info.protection&(VM_PROT_READ|VM_PROT_WRITE))==(VM_PROT_READ|VM_PROT_WRITE);
}
static void consider_image(const struct mach_header *header,intptr_t slide) {
    int saved_errno=errno;Dl_info info={0};
    if(!dladdr(header,&info)||!info.dli_fname||!target_image_name(info.dli_fname)||header->magic!=MH_MAGIC_64) goto done;
    const struct mach_header_64 *mh=(const void *)header;
    if(mh->sizeofcmds>65536||mh->ncmds>512) goto done;
    static const unsigned char uuid[16]={0x44,0x18,0xec,0x47,0xc3,0xf0,0x32,0x85,0xa0,0x56,0x15,0xd8,0x7d,0x78,0x5f,0xfe};
    bool matched=false;
    const unsigned char *begin=(const void *)(mh+1),*at=begin;
    for(uint32_t i=0;i<mh->ncmds;++i) {
        if(at+sizeof(struct load_command)>begin+mh->sizeofcmds) goto done;
        const struct load_command *lc=(const void *)at;
        if(lc->cmdsize<sizeof *lc||at+lc->cmdsize>begin+mh->sizeofcmds) goto done;
        if(lc->cmd==LC_UUID&&lc->cmdsize==sizeof(struct uuid_command)) matched=!memcmp(((const struct uuid_command *)lc)->uuid,uuid,16);
        at+=lc->cmdsize;
    }
    uintptr_t ds=(uintptr_t)slide+DIRECT_SLOT,us=(uintptr_t)slide+UNPACK_SLOT;
    uintptr_t dm=(uintptr_t)slide+DIRECT_METHOD,um=(uintptr_t)slide+UNPACK_METHOD;
    bool installed_direct=false,installed_unpack=false;
    if(matched&&writable(ds)&&writable(us)) {
        uintptr_t a=atomic_load((_Atomic uintptr_t *)ds),b=atomic_load((_Atomic uintptr_t *)us);
        if(a==dm&&b==um) {
            original_direct=(Direct)dm;original_unpack=(Unpack)um;
            installed_direct=atomic_compare_exchange_strong((_Atomic uintptr_t *)ds,&a,(uintptr_t)&observe_direct);
            if(installed_direct) installed_unpack=atomic_compare_exchange_strong((_Atomic uintptr_t *)us,&b,(uintptr_t)&observe_unpack);
            if(installed_direct&&!installed_unpack) {
                uintptr_t own=(uintptr_t)&observe_direct;
                atomic_compare_exchange_strong((_Atomic uintptr_t *)ds,&own,dm);installed_direct=false;
            }
        }
    }
    char line[320];int n=snprintf(line,sizeof line,
        "SP26_CAPABILITY {\"event\":\"install\",\"pid\":%d,\"uuid_matched\":%s,\"direct_installed\":%s,\"unpack_installed\":%s,\"mask_enabled\":%s}\n",
        getpid(),matched?"true":"false",installed_direct?"true":"false",installed_unpack?"true":"false",CAP_MASK?"true":"false");
    emit(line,n,sizeof line);
done: errno=saved_errno;
}
__attribute__((constructor)) static void loaded(void) {
    int saved_errno=errno;Dl_info own={0};
    bool pinned=dladdr((const void *)&loaded,&own)&&own.dli_fname&&dlopen(own.dli_fname,RTLD_NOW|RTLD_NOLOAD|RTLD_NODELETE);
    char line[224];int n=snprintf(line,sizeof line,
        "SP26_CAPABILITY {\"event\":\"loaded\",\"pid\":%d,\"pinned\":%s,\"mask_enabled\":%s}\n",
        getpid(),pinned?"true":"false",CAP_MASK?"true":"false");
    emit(line,n,sizeof line);
    if(pinned) _dyld_register_func_for_add_image(consider_image);
    errno=saved_errno;
}
#endif

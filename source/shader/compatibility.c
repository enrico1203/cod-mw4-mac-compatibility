/* Default-enabled shader compatibility. Two exact shader hashes only. */
#include "observer.c"
#include <CommonCrypto/CommonDigest.h>
#include <stdlib.h>

typedef struct {const void*data;size_t size;} CullBytecode;
typedef struct {void*root;CullBytecode cs;uint32_t node;CullBytecode cached;uint32_t flags;} CullCompute;
typedef struct {size_t size;const void*data;} CullStream;
#ifndef CULL_REPLACEMENT_HEADER
#define CULL_REPLACEMENT_HEADER "replacement_data.h"
#endif
#include CULL_REPLACEMENT_HEADER
typedef int32_t (__attribute__((ms_abi)) *CullDirect)(void*,const void*,const void*,void**);
typedef int32_t (__attribute__((ms_abi)) *CullLibrary)(void*,const void*,const void*,const void*,void**);
typedef struct {void*object;const void*desc;const void*iid;void**output;int32_t hr;} CullParams;
typedef struct {void*object;const void*name;const void*desc;const void*iid;void**output;int32_t hr;} CullLibParams;
typedef int32_t (*CullUnpack)(void*);
_Static_assert(sizeof(CullCompute)==56&&offsetof(CullCompute,cached)==32,"D3D12 compute ABI");
_Static_assert(sizeof(CullParams)==40&&offsetof(CullParams,hr)==32,"device unpack ABI");
_Static_assert(sizeof(CullLibParams)==48&&offsetof(CullLibParams,hr)==40,"library unpack ABI");
static CullDirect c_compute,c_stream;
static CullLibrary c_lib_compute,c_lib_stream;
static CullUnpack c_un_compute,c_un_stream,c_un_lib_compute,c_un_lib_stream;
static uint32_t c_u32(const void*p){uint32_t n;memcpy(&n,p,4);return n;}
static void c_log(const char*s){(void)write(2,s,strlen(s));}
/* Windows x64 subobject sizes from pinned DirectX-Headers definitions.
 * Pointer-aligned objects; unknown/reserved types are never traversed. */
static const uint16_t c_sizes[]={16,24,24,24,24,24,24,40,336,8,48,56,24,8,8,40,8,16,8,24,8,64,32,0,24,24,64,48,48,24};
static CullBytecode* c_stream_cs(const CullStream*d){
 if(!d||!d->data||d->size>65536||(d->size&7))return NULL;
 size_t at=0;CullBytecode*found=NULL;const unsigned char*p=d->data;
 while(at<d->size){if(d->size-at<8)return NULL;uint32_t t=c_u32(p+at);
  if(t>=sizeof c_sizes/sizeof c_sizes[0]||!c_sizes[t]||c_sizes[t]>d->size-at){return NULL;}
  if(t==6){if(found)return NULL;found=(CullBytecode*)(p+at+8);}at+=c_sizes[t];
 }
 return found;
}
typedef struct {CullCompute compute;CullStream stream;const void*desc;void*allocation;int target;} CullPrepared;
static _Atomic unsigned c_reported[2];
static void c_prepare(CullPrepared*p,const void*d,bool stream,const char*route){
 int saved=errno;memset(p,0,sizeof(*p));p->desc=d;p->target=-1;(void)route;
#ifdef CULL_REPLACEMENT_HEADER
 if(d){
  const CullBytecode*source=stream?c_stream_cs(d):&((const CullCompute*)d)->cs;
  if(source&&source->data){
   bool possible=false;for(unsigned j=0;j<sizeof c_replacements/sizeof c_replacements[0];j++)if(source->size==c_replacements[j].original_size)possible=true;
   if(possible){unsigned char hash[32];CC_SHA256(source->data,(CC_LONG)source->size,hash);
    for(unsigned j=0;j<sizeof c_replacements/sizeof c_replacements[0];j++)if(source->size==c_replacements[j].original_size&&!memcmp(hash,c_replacements[j].original_hash,32)){
     CullBytecode replacement={c_replacements[j].replacement,c_replacements[j].replacement_size};
     if(stream){
      p->stream=*(const CullStream*)d;p->allocation=malloc(p->stream.size);if(!p->allocation){c_log("SP26_SHADER_COMPAT {\"event\":\"replacement_allocation_failed\"}\n");break;}
      memcpy(p->allocation,p->stream.data,p->stream.size);size_t offset=(const unsigned char*)source-(const unsigned char*)p->stream.data;
      memcpy((unsigned char*)p->allocation+offset,&replacement,sizeof replacement);p->stream.data=p->allocation;p->desc=&p->stream;
      for(size_t at=0;at<p->stream.size;){uint32_t t=c_u32((const unsigned char*)p->stream.data+at);if(t==19)memset((unsigned char*)p->allocation+at+8,0,sizeof(CullBytecode));at+=c_sizes[t];}
     }else{p->compute=*(const CullCompute*)d;p->compute.cs=replacement;p->compute.cached=(CullBytecode){NULL,0};p->desc=&p->compute;}
     p->target=(int)j;break;
    }
   }
  }
 }
#endif
 errno=saved;
}
static void c_done(CullPrepared*p,int32_t hr,const char*route){
 int saved=errno;
 if(p->target>=0&&hr>=0){unsigned j=(unsigned)p->target;if(atomic_fetch_add(&c_reported[j],1)==0){char l[400];snprintf(l,sizeof l,"SP26_SHADER_COMPAT {\"event\":\"accepted\",\"entry\":\"%s\",\"route\":\"%s\",\"hresult\":%u}\n",c_replacements[j].entry,route,(uint32_t)hr);c_log(l);}}
 free(p->allocation);errno=saved;
}
static int32_t __attribute__((ms_abi)) c_do_compute(void*o,const void*d,const void*i,void**p){CullPrepared t;c_prepare(&t,d,false,"device-direct");int32_t hr=c_compute(o,t.desc,i,p);c_done(&t,hr,"device-direct");return hr;}
static int32_t __attribute__((ms_abi)) c_do_stream(void*o,const void*d,const void*i,void**p){CullPrepared t;c_prepare(&t,d,true,"stream-direct");int32_t hr=c_stream(o,t.desc,i,p);c_done(&t,hr,"stream-direct");return hr;}
static int32_t __attribute__((ms_abi)) c_do_lib_compute(void*o,const void*n,const void*d,const void*i,void**p){CullPrepared t;c_prepare(&t,d,false,"library-direct");int32_t hr=c_lib_compute(o,n,t.desc,i,p);c_done(&t,hr,"library-direct");return hr;}
static int32_t __attribute__((ms_abi)) c_do_lib_stream(void*o,const void*n,const void*d,const void*i,void**p){CullPrepared t;c_prepare(&t,d,true,"library-stream-direct");int32_t hr=c_lib_stream(o,n,t.desc,i,p);c_done(&t,hr,"library-stream-direct");return hr;}
static int32_t c_do_un_compute(void*x){CullParams*p=x,v=*p;CullPrepared t;c_prepare(&t,p->desc,false,"device-unpack");v.desc=t.desc;int32_t status=c_un_compute(&v);p->hr=v.hr;c_done(&t,v.hr,"device-unpack");return status;}
static int32_t c_do_un_stream(void*x){CullParams*p=x,v=*p;CullPrepared t;c_prepare(&t,p->desc,true,"stream-unpack");v.desc=t.desc;int32_t status=c_un_stream(&v);p->hr=v.hr;c_done(&t,v.hr,"stream-unpack");return status;}
static int32_t c_do_un_lib_compute(void*x){CullLibParams*p=x,v=*p;CullPrepared t;c_prepare(&t,p->desc,false,"library-unpack");v.desc=t.desc;int32_t status=c_un_lib_compute(&v);p->hr=v.hr;c_done(&t,v.hr,"library-unpack");return status;}
static int32_t c_do_un_lib_stream(void*x){CullLibParams*p=x,v=*p;CullPrepared t;c_prepare(&t,p->desc,true,"library-stream-unpack");v.desc=t.desc;int32_t status=c_un_lib_stream(&v);p->hr=v.hr;c_done(&t,v.hr,"library-stream-unpack");return status;}
static void c_image(const struct mach_header*h,intptr_t slide){
 int saved=errno;Dl_info info={0};if(!dladdr(h,&info)||!target_image_name(info.dli_fname)||h->magic!=MH_MAGIC_64)goto done;
 const struct mach_header_64*mh=(const void*)h;const unsigned char*begin=(const void*)(mh+1),*at=begin;
 static const unsigned char uuid[16]={0x44,0x18,0xec,0x47,0xc3,0xf0,0x32,0x85,0xa0,0x56,0x15,0xd8,0x7d,0x78,0x5f,0xfe};bool matched=false;
 if(mh->sizeofcmds>65536||mh->ncmds>512)goto done;
 for(uint32_t j=0;j<mh->ncmds;j++){if(at+sizeof(struct load_command)>begin+mh->sizeofcmds)goto done;const struct load_command*l=(const void*)at;if(l->cmdsize<sizeof(*l)||at+l->cmdsize>begin+mh->sizeofcmds)goto done;if(l->cmd==LC_UUID&&l->cmdsize==sizeof(struct uuid_command))matched=!memcmp(((const struct uuid_command*)l)->uuid,uuid,16);at+=l->cmdsize;}
 struct {uintptr_t slot,method;void*hook;} entries[]={
  {0x527f68,0x70a20,c_do_compute},{0x528208,0x80ccf,c_do_un_compute},
  {0x528088,0x713a5,c_do_stream},{0x528328,0x81386,c_do_un_stream},
  {0x527e70,0x6588c,c_do_lib_compute},{0x527ef0,0x68f60,c_do_un_lib_compute},
  {0x527e88,0x658a7,c_do_lib_stream},{0x527f08,0x68fcc,c_do_un_lib_stream}};
 for(unsigned j=0;j<8;j++)if(!method_contract(slide+entries[j].method,entries[j].method)||!writable(slide+entries[j].slot)||__atomic_load_n((uintptr_t*)(slide+entries[j].slot),__ATOMIC_ACQUIRE)!=slide+entries[j].method){c_log("SP26_SHADER_COMPAT {\"event\":\"install_refused\",\"reason\":\"method_or_dispatch_layout\"}\n");goto done;}
 c_compute=(CullDirect)(slide+0x70a20);c_un_compute=(CullUnpack)(slide+0x80ccf);c_stream=(CullDirect)(slide+0x713a5);c_un_stream=(CullUnpack)(slide+0x81386);c_lib_compute=(CullLibrary)(slide+0x6588c);c_un_lib_compute=(CullUnpack)(slide+0x68f60);c_lib_stream=(CullLibrary)(slide+0x658a7);c_un_lib_stream=(CullUnpack)(slide+0x68fcc);
 for(unsigned j=0;j<8;j++){uintptr_t expected=slide+entries[j].method;if(!__atomic_compare_exchange_n((uintptr_t*)(slide+entries[j].slot),&expected,(uintptr_t)entries[j].hook,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)){
  for(unsigned k=0;k<j;k++){uintptr_t ours=(uintptr_t)entries[k].hook;(void)__atomic_compare_exchange_n((uintptr_t*)(slide+entries[k].slot),&ours,slide+entries[k].method,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);}c_log("SP26_SHADER_COMPAT {\"event\":\"install_conflict\"}\n");goto done;}}
#ifdef CULL_REPLACEMENT_HEADER
 c_log(matched?"SP26_SHADER_COMPAT {\"event\":\"installed\",\"uuid_matched\":true,\"layout_verified\":true,\"replacement_enabled\":true,\"exact_hashes_only\":true,\"slots\":8}\n":"SP26_SHADER_COMPAT {\"event\":\"installed\",\"uuid_matched\":false,\"layout_verified\":true,\"replacement_enabled\":true,\"exact_hashes_only\":true,\"slots\":8}\n");
#else
 c_log("SP26_SHADER_COMPAT {\"event\":\"installed\",\"uuid_matched\":true,\"input_unchanged\":true,\"slots\":8}\n");
#endif
 done:errno=saved;
}
__attribute__((constructor))static void c_init(void){_dyld_register_func_for_add_image(c_image);}

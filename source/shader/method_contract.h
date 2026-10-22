#include "method_bytes.h"
/* Point-of-use method verification; accepts unrelated module/UUID changes. */
static bool method_contract(uintptr_t address,uintptr_t method){
 const unsigned char*expected=NULL;
 for(size_t i=0;i<sizeof method_windows/sizeof method_windows[0];i++)
  if(method_windows[i].at==method){expected=method_windows[i].bytes;break;}
 if(!expected)return false;
 mach_vm_address_t start=address;mach_vm_size_t length=0;
 vm_region_basic_info_data_64_t info;
 mach_msg_type_number_t count=VM_REGION_BASIC_INFO_COUNT_64;
 mach_port_t object=MACH_PORT_NULL;
 kern_return_t result=mach_vm_region(mach_task_self(),&start,&length,VM_REGION_BASIC_INFO_64,(vm_region_info_t)&info,&count,&object);
 if(object)mach_port_deallocate(mach_task_self(),object);
 if(result!=KERN_SUCCESS||start>address||length<64||address-start>length-64||
    (info.protection&(VM_PROT_READ|VM_PROT_EXECUTE))!=(VM_PROT_READ|VM_PROT_EXECUTE))return false;
 return !memcmp((const void*)address,expected,64);
}

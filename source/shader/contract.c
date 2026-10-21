#define CAP_CONTRACT_TEST 1
#include "observer.c"
#include <assert.h>
static unsigned calls;
static uint32_t advertised=1;
static int32_t forced_hr,forced_status;
static int32_t __attribute__((ms_abi)) fake_direct(void *device,uint32_t feature,void *data,uint32_t size) {
    assert(device==(void *)0x1234);++calls;errno=EDOM;
    if(forced_hr) return forced_hr;
    if(!data||size!=20) return (int32_t)0x80070057;
    Options3 value={0,1,13,2,advertised};
    if(feature!=21) value.barycentrics=0xdeadbeef;
    memcpy(data,&value,20);return 0;
}
static int32_t fake_unpack(Params *p) {
    if(forced_status) {errno=EDOM;return forced_status;}
    p->hr=fake_direct(p->device,p->feature,p->data,p->size);return 0;
}
int main(void) {
    assert(target_image_name("/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/lib/apple_gptk/external/D3DMetal.framework/Versions/A/D3DMetal"));
    assert(target_image_name("/Applications/CrossOver Preview.app/Contents/SharedSupport/CrossOver/lib/apple_gptk/external/D3DMetal.framework/Versions/A/D3DMetal"));
    assert(target_image_name("/Users/example/Applications/Renamed App.app/D3DMetal"));
    assert(target_image_name("D3DMetal"));
    assert(!target_image_name(NULL));
    assert(!target_image_name(""));
    assert(!target_image_name("/tmp/OtherD3DMetal"));
    assert(!target_image_name("/tmp/D3DMetal.backup"));
    assert(!target_image_name("/tmp/D3DMetal/"));
    assert(!target_image_name("/tmp/D3DMetal/other"));
    original_direct=fake_direct;original_unpack=fake_unpack;
    for(int route=0;route<2;++route) for(int scenario=0;scenario<7;++scenario) {
        struct {uint64_t before;Options3 value;uint32_t after;} guarded={0xaabbccdd11223344ULL,{9,8,7,6,5},0x12345678};
        Options3 saved=guarded.value;
        uint32_t feature=scenario==1?8:21,size=scenario==2?19:20;
        advertised=scenario==4?0:scenario==5?0xfeed:1;
        forced_hr=scenario==3?(int32_t)0x80004005:0;
        forced_status=scenario==6&&route==1?(int32_t)0xc0000001:0;
        Params p={(void *)0x1234,feature,0,&guarded.value,size,0x123};
        int32_t hr,status=0;errno=0;
        if(route) {status=observe_unpack(&p);hr=p.hr;}
        else hr=observe_direct(p.device,p.feature,p.data,p.size);
        assert(errno==EDOM);
        assert(guarded.before==0xaabbccdd11223344ULL&&guarded.after==0x12345678);
        if(forced_status) {assert(status==forced_status&&hr==0x123);assert(!memcmp(&saved,&guarded.value,20));}
        else if(forced_hr||size!=20) {assert(hr==(forced_hr?forced_hr:(int32_t)0x80070057));assert(!memcmp(&saved,&guarded.value,20));}
        else {
            assert(hr==0&&guarded.value.copy_timestamps==0&&guarded.value.typed_cast==1&&guarded.value.write_flags==13&&guarded.value.view_tier==2);
            assert(guarded.value.barycentrics==(feature!=21?0xdeadbeef:CAP_MASK&&advertised==1?0:advertised));
        }
    }
    assert(calls==13);
    printf("CONTRACT_PASS mask=%d cases=14 direct_and_unixcall return_errno_other_fields_and_canaries_preserved\n",CAP_MASK);
    return 0;
}

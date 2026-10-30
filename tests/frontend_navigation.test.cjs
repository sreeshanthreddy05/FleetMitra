const {test}=require('node:test');const assert=require('node:assert/strict');
const geometry=require('../static/js/navigation_geometry.js');
test('geometry progress follows bends and clamps at route ends',()=>{const p=[[78,17],[78.01,17],[78.01,17.01]];const length=geometry.meters(p[0],p[1]);const half=geometry.split(p,length);assert(Math.abs(half.remaining[0][0]-78.01)<1e-8);assert.equal(half.remaining[0][1],17);assert.deepEqual(geometry.split(p,1e9).travelled,p);assert.deepEqual(geometry.split(p,-1).remaining[0],p[0]);});
test('follow zooms to 17; manual exploration preserves zoom',()=>{assert.deepEqual(geometry.cameraState({following:false,zoom:12},'FOLLOW'),{following:true,zoom:17});assert.deepEqual(geometry.cameraState({following:true,zoom:16},'EXPLORE'),{following:false,zoom:16});});
test('navigation bearing rotates north and east correctly',()=>{assert.equal(geometry.bearing([78,17],[78,18]),0);assert(Math.abs(geometry.bearing([78,17],[79,17])-90)<1e-8);});

/* Pure geometry used by live and historical map rendering. GeoJSON is [lon,lat]. */
((root) => {
  const meters=(a,b)=>{const r=x=>x*Math.PI/180,dlat=r(b[1]-a[1]),dlon=r(b[0]-a[0]);return 12742000*Math.asin(Math.min(1,Math.sqrt(Math.sin(dlat/2)**2+Math.cos(r(a[1]))*Math.cos(r(b[1]))*Math.sin(dlon/2)**2)));};
  function split(points,distance){if(points.length<2)return {travelled:[],remaining:points};let walked=0;for(let i=1;i<points.length;i++){const length=meters(points[i-1],points[i]);if(walked+length>=distance){const t=length?Math.max(0,Math.min(1,(distance-walked)/length)):0;const point=points[i-1].map((v,k)=>v+(points[i][k]-v)*t);return {travelled:[...points.slice(0,i),point],remaining:[point,...points.slice(i)]};}walked+=length;}return {travelled:points,remaining:[points.at(-1)]};}
  function bearing(a,b){return Math.atan2((b[0]-a[0])*Math.cos((a[1]+b[1])/2*Math.PI/180),b[1]-a[1])*180/Math.PI;}
  function cameraState(state,action){return {following:action==='FOLLOW',zoom:action==='FOLLOW'?17:state.zoom};}
  const api={meters,split,bearing,cameraState};root.NavigationGeometry=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);

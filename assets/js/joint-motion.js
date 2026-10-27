// Bounded motion for every independent joint, with shared tracks for mirror pairs.
const clamp = (x, low, high) => Math.max(low, Math.min(high, x));
function amplitude(control, span, category) {
  const group=control.group.toLowerCase();
  const cap=control.unit==='m'?.02:/mobile base|wheel/.test(group)?.55:
    /torso/.test(group)?.14:/head/.test(group)?.18:
    control.name.includes('_hand/')||category!=='manipulator'?.4:.22;
  return Math.min(span*.18,cap);
}
export function createMotionPlan(model, start, dependent=()=>false) {
  const enabled=new Map(model.controls.filter(c=>c.upper-c.lower>1e-8&&!dependent(c.name)).map(c=>[c.name,c]));
  const tracks=[],claimed=new Set();
  for(const pair of model.motion_pairs||[]){
    const left=enabled.get(pair.left),right=enabled.get(pair.right);
    if(!left||!right||claimed.has(left.name)||claimed.has(right.name))continue;
    const sign=pair.sign,offset=pair.offset||0;
    const low=Math.max(left.lower,sign>0?right.lower-offset:offset-right.upper);
    const high=Math.min(left.upper,sign>0?right.upper-offset:offset-right.lower);
    if(high-low<1e-8)continue;
    const size=amplitude(left,high-low,model.category);
    const center=clamp((start[left.name]+(start[right.name]-offset)/sign)/2,low+size,high-size);
    tracks.push({left:left.name,right:right.name,sign,offset,center,amplitude:size});
    claimed.add(left.name);claimed.add(right.name);
  }
  for(const c of enabled.values()){
    if(claimed.has(c.name))continue;
    const size=amplitude(c,c.upper-c.lower,model.category);
    tracks.push({left:c.name,center:clamp(start[c.name],c.lower+size,c.upper-size),amplitude:size});
  }
  return tracks;
}
export function sampleMotion(plan,start,elapsedMs){
  const q={...start},blend=Math.min(1,elapsedMs/700),wave=Math.sin(elapsedMs*.00125);
  for(const track of plan){
    const value=track.center+track.amplitude*wave;
    q[track.left]=start[track.left]*(1-blend)+value*blend;
    if(track.right)q[track.right]=start[track.right]*(1-blend)+(track.sign*value+track.offset)*blend;
  }
  return q;
}

/** Incremental UTF-8 SSE decoder; transport fragments need not align with events. */
export async function readEventStream(body:ReadableStream<Uint8Array>, signal:AbortSignal,
  receive:(type:string,data:string)=>void) {
  const reader=body.getReader(), decoder=new TextDecoder()
  let pending='', type='message', data:string[]=[]
  const abort=()=>{void reader.cancel().catch(()=>{})}
  signal.addEventListener('abort',abort,{once:true})
  try {
    while(!signal.aborted) {
      const chunk=await reader.read()
      if(chunk.done) break
      pending+=decoder.decode(chunk.value,{stream:true})
      if(pending.length+data.join('').length>1048576) throw new Error('会话事件超过允许大小')
      let end:number
      while((end=pending.indexOf('\n'))>=0) {
        const line=pending.slice(0,end).replace(/\r$/,''); pending=pending.slice(end+1)
        if(!line) {
          if(data.length) receive(type,data.join('\n'))
          type='message'; data=[]
        } else if(line.startsWith('event:')) type=line.slice(6).trimStart()
        else if(line.startsWith('data:')) data.push(line.slice(5).replace(/^ /,''))
      }
    }
    if(!signal.aborted && (pending.trim() || data.length)) throw new Error('会话事件接收不完整')
  } finally {
    signal.removeEventListener('abort',abort)
    await reader.cancel().catch(()=>{})
    reader.releaseLock()
  }
}

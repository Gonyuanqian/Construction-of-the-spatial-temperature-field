import { assistantApi, type AssistantRun, type Conversation } from '../api/assistant'
import { ApiError } from '../api/client'
import { ConversationAssembler, isActiveRun, type ConversationTurn } from './conversation'

type Transport=Pick<typeof assistantApi,'run'|'conversation'> & Partial<Pick<typeof assistantApi,'stream'>>
export type ConnectionState='idle'|'streaming'|'reconnecting'|'polling'

/** Owns connection generation, cursor and cancellation. Vue only receives snapshots. */
export class ConversationSession {
  private io:Transport
  private publish:(turns:readonly ConversationTurn[],state:ConnectionState)=>void
  private model=new ConversationAssembler()
  private id=''
  private generation=0
  private abort?:AbortController
  private timer?:ReturnType<typeof setTimeout>
  private failures=0
  private fallbackRounds=0
  constructor(io:Transport,publish:(turns:readonly ConversationTurn[],state:ConnectionState)=>void) {
    this.io=io; this.publish=publish
  }
  close() {this.generation++;this.abort?.abort();clearTimeout(this.timer)}
  open(id:string, snapshot:Conversation) {
    this.close()
    if(this.id!==id) this.model=new ConversationAssembler()
    this.id=id;this.failures=0;this.fallbackRounds=0;this.model.replace(snapshot)
    this.emit('idle');void this.pump(this.generation)
  }
  follow(id:string,runs:AssistantRun[]) {
    this.close()
    if(this.id!==id) {this.model=new ConversationAssembler();this.id=id}
    for(const run of runs) this.model.upsert(run)
    this.failures=0;this.fallbackRounds=0
    this.emit('idle');void this.pump(this.generation)
  }
  accept(run:AssistantRun) {this.model.upsert(run);this.emit('idle')}
  private emit(state:ConnectionState) {this.publish(this.model.snapshot(),state)}
  private schedule(generation:number,ms:number) {
    if(generation===this.generation) this.timer=setTimeout(()=>{void this.pump(generation)},ms)
  }
  private async pump(generation:number) {
    if(generation!==this.generation) return
    const head=this.model.snapshot().at(-1)?.run
    if(!isActiveRun(head)) {this.emit('idle');return}
    this.abort=new AbortController()
    if(this.io.stream && this.failures<2) {
      const before=this.model.cursor
      this.emit(this.failures ? 'reconnecting' : 'streaming')
      try {
        await this.io.stream(this.id,this.model.cursor,this.abort.signal,event=>{
          if(generation===this.generation && this.model.append(event)) this.emit('streaming')
        })
        if(generation!==this.generation) return
        this.failures=this.model.cursor===before ? this.failures+1 : 0
      } catch(error) {
        if(generation!==this.generation) return
        this.failures++
        // Rebuild the same model from an atomic snapshot on a gap or cursor rejection.
        if(!(error instanceof ApiError) || error.status===409) {
          try {
            const snapshot=await this.io.conversation(this.id)
            if(generation!==this.generation) return
            this.model.replace(snapshot);this.emit('reconnecting')
          } catch { /* retain the last trustworthy window until the next retry */ }
        }
      }
      this.schedule(generation,Math.min(4000,250*2**this.failures))
    } else {
      this.emit('polling')
      try {
        const run=await this.io.run(head!.id)
        if(generation!==this.generation) return
        this.model.upsert(run);this.emit('polling')
      } catch {if(generation===this.generation) this.emit('reconnecting')}
      if(++this.fallbackRounds>=5) {this.failures=0;this.fallbackRounds=0}
      this.schedule(generation,1000)
    }
  }
}

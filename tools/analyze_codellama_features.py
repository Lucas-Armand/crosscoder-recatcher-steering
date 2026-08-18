#!/usr/bin/env python3
"""Build interpretation artifacts for selected DSTK100 features."""
import argparse,csv,json,heapq,collections
from pathlib import Path
import numpy as np,torch
from transformers import AutoTokenizer

def main():
 p=argparse.ArgumentParser();p.add_argument("--checkpoint",type=Path,required=True);p.add_argument("--activation-root",type=Path,required=True);p.add_argument("--labels",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--features",type=int,nargs="+",required=True);p.add_argument("--device",default="cuda:0");p.add_argument("--contexts",type=int,default=40);p.add_argument("--model-a-label",default="deepseek_base");p.add_argument("--model-b-label",default="deepseek_finetuned");p.add_argument("--tokenizer",default="JetBrains/deepseek-coder-6.7B-kexer");a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 ck=torch.load(a.checkpoint,map_location="cpu",weights_only=False);sd=ck["model_state_dict"];dev=torch.device(a.device);w=sd["encoder.weight"].float().to(dev);bias=sd["encoder.bias"].float().to(dev);k=int(ck["config"]["top_k"]);hidden=sd["decoder_a.weight"].shape[0]
 da=sd["decoder_a.weight"].float();db=sd["decoder_b.weight"].float();wa=sd["encoder.weight"][:,:hidden].float();wb=sd["encoder.weight"][:,hidden:].float()
 labels={}
 for r in csv.DictReader(a.labels.open()):
  if int(r["generation_idx"])==0 and r["model"] in (a.model_a_label,a.model_b_label):labels[(r["model"],r["benchmark"],r["task_id"])]=int(r["label"])
 tok=AutoTokenizer.from_pretrained(a.tokenizer,trust_remote_code=True,local_files_only=True)
 manifest=json.loads((a.activation_root/"capture_manifest.json").read_text());task_rows=[];heaps={f:[] for f in a.features};token_stats={f:collections.defaultdict(lambda:[0,0.]) for f in a.features}
 for ix,m in enumerate(manifest,1):
  xa=np.load(a.activation_root/m["benchmark"]/a.model_a_label/m["filename"]);xb=np.load(a.activation_root/m["benchmark"]/a.model_b_label/m["filename"]);ids=xa["input_ids"]
  x=torch.from_numpy(np.concatenate((xa["layer_16"],xb["layer_16"]),1)).float().to(dev)
  with torch.inference_mode():
   dense=torch.relu(torch.nn.functional.linear(x,w,bias));v,ind=torch.topk(dense,k,dim=1,sorted=False)
   ca=torch.nn.functional.linear(x[:,:hidden],w[:, :hidden],None);cb=torch.nn.functional.linear(x[:,hidden:],w[:,hidden:],None)
   for fid in a.features:
    q=torch.where(ind==fid,v,torch.zeros_like(v)).sum(1);active=q>0;n=len(q);mx=float(q.max());arg=int(q.argmax());act_idx=torch.nonzero(active).flatten().cpu().tolist()
    lb=labels[(a.model_a_label,m["benchmark"],m["task_id"])];lf=labels[(a.model_b_label,m["benchmark"],m["task_id"])]
    tr="regression" if lb==0 and lf==1 else "improvement" if lb==1 and lf==0 else "both_pass" if lb==0 else "both_fail"
    task_rows.append({"feature_id":fid,**m,"transition":tr,"base_label":lb,"finetuned_label":lf,"max_activation":mx,"mean_activation":float(q.mean()),"early_max_activation":float(q[:max(1,(n+3)//4)].max()),"active_tokens":len(act_idx),"active_fraction":len(act_idx)/n,"first_position":act_idx[0] if act_idx else -1,"first_percent":100*act_idx[0]/n if act_idx else -1,"argmax_position":arg,"argmax_percent":100*arg/n,"encoder_base_contribution_at_max":float(ca[arg,fid]),"encoder_finetuned_contribution_at_max":float(cb[arg,fid]),"token_at_max":tok.decode([int(ids[arg])],clean_up_tokenization_spaces=False),"context_at_max":tok.decode(ids[max(0,arg-16):min(n,arg+17)].tolist(),clean_up_tokenization_spaces=False).replace("\n","\\n")})
    item=(mx,ix,{"feature_id":fid,**m,"transition":tr,"max_activation":mx,"position":arg,"position_percent":100*arg/n,"token_text":tok.decode([int(ids[arg])],clean_up_tokenization_spaces=False),"context":tok.decode(ids[max(0,arg-24):min(n,arg+25)].tolist(),clean_up_tokenization_spaces=False).replace("\n","\\n"),"encoder_base_contribution":float(ca[arg,fid]),"encoder_finetuned_contribution":float(cb[arg,fid])})
    if len(heaps[fid])<a.contexts:heapq.heappush(heaps[fid],item)
    elif mx>heaps[fid][0][0]:heapq.heapreplace(heaps[fid],item)
    for j in act_idx:
     s=tok.decode([int(ids[j])],clean_up_tokenization_spaces=False);token_stats[fid][s][0]+=1;token_stats[fid][s][1]+=float(q[j])
  if ix%200==0:print(ix,flush=True)
 fields=list(task_rows[0]);f=open(a.output/"feature_task_statistics.csv","w",newline="");wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(task_rows);f.close()
 contexts=[]
 for fid in a.features:
  for rank,(_,_,r) in enumerate(sorted(heaps[fid],reverse=True),1):contexts.append({"rank":rank,**r})
 f=open(a.output/"top_activating_contexts.csv","w",newline="");wr=csv.DictWriter(f,fieldnames=list(contexts[0]));wr.writeheader();wr.writerows(contexts);f.close()
 geom=[];tokens=[]
 for fid in a.features:
  nba=float(torch.linalg.vector_norm(da[:,fid]));nbb=float(torch.linalg.vector_norm(db[:,fid]));cosd=float(torch.nn.functional.cosine_similarity(da[:,fid],db[:,fid],dim=0));nea=float(torch.linalg.vector_norm(wa[fid]));neb=float(torch.linalg.vector_norm(wb[fid]));cose=float(torch.nn.functional.cosine_similarity(wa[fid],wb[fid],dim=0))
  rr=[r for r in task_rows if r["feature_id"]==fid];geom.append({"feature_id":fid,"decoder_base_norm":nba,"decoder_finetuned_norm":nbb,"decoder_cosine":cosd,"decoder_difference_norm":float(torch.linalg.vector_norm(db[:,fid]-da[:,fid])),"encoder_base_half_norm":nea,"encoder_finetuned_half_norm":neb,"encoder_half_cosine":cose,"active_texts":sum(r["active_tokens"]>0 for r in rr),"active_tokens":sum(r["active_tokens"] for r in rr)})
  for rank,(token,(count,total)) in enumerate(sorted(token_stats[fid].items(),key=lambda x:(x[1][1],x[1][0]),reverse=True)[:30],1):tokens.append({"feature_id":fid,"rank":rank,"token_text":token,"active_occurrences":count,"activation_sum":total,"mean_activation":total/count})
 for name,rows in (("feature_geometry.csv",geom),("top_active_tokens.csv",tokens)):
  f=open(a.output/name,"w",newline="");wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows);f.close()
 (a.output/"run_summary.json").write_text(json.dumps({"checkpoint":str(a.checkpoint),"step":ck["step"],"top_k":k,"features":a.features,"texts":len(manifest),"mask":"evaluated extraction-v4 code tokens","contexts_per_feature":a.contexts},indent=2)+"\n")
if __name__=="__main__":main()

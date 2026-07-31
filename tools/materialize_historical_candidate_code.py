#!/usr/bin/env python3
"""Apply the original notebook's candidate-code heuristic verbatim."""
import argparse,json
from pathlib import Path

def strip_markdown_fences(text):
    text=text.replace("```python","```")
    if "```" in text:
        parts=text.split("```")
        if len(parts)>=3:return max(parts[1::2],key=len).strip("\n")
    return text.strip("\n")

def truncate_completion(completion):
    markers=["\n\nif __name__","\nif __name__","\n\n# Test","\n# Test","\n\n# test","\n# test","\n\nprint(","\nprint(","\n\nassert ","\nassert ","\n\nExplanation:","\nExplanation:","\n\nThe function","\nThe function","\n\nThis function","\nThis function","\n```"]
    cut=len(completion)
    for marker in markers:
        index=completion.find(marker)
        if index!=-1:cut=min(cut,index)
    for pattern in ["\n\ndef ","\n\n\ndef "]:
        index=completion.find(pattern)
        if index!=-1:cut=min(cut,index)
    return completion[:cut].rstrip()+"\n"

def make_candidate(prompt,completion,entry_point):
    cleaned=truncate_completion(strip_markdown_fences(completion))
    index=cleaned.find(f"def {entry_point}")
    return (cleaned[index:].rstrip()+"\n") if index!=-1 else (prompt.rstrip()+"\n"+cleaned.rstrip()+"\n")

def main():
    p=argparse.ArgumentParser();p.add_argument("input",type=Path);p.add_argument("output",type=Path);a=p.parse_args()
    rows=[]
    for line in a.input.read_text().splitlines():
        if not line.strip():continue
        row=json.loads(line)
        historical=make_candidate(row["prompt"],row["completion"],row["entry_point"])
        row["candidate_code_historical"]=historical
        row["candidate_code_original"]=historical
        rows.append(row)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text("".join(json.dumps(row)+"\n" for row in rows))
    print(json.dumps({"rows":len(rows),"output":str(a.output)}))
if __name__=="__main__":main()

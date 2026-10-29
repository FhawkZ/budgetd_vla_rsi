"""Read-only evidence tools for persistent roles; no shell, writes or network.
Only explicitly configured real directories are reachable. Symlink escapes and
sensitive filenames are rejected. The script itself never runs generated code.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, time
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations

DENIED_PARTS={'.git','.ssh','.aws','.azure','.config','.codex','codex-home'}
DENIED_NAMES={'auth.json','credentials','credentials.json','config.toml','.env'}
class Scope:
    def __init__(self, roots, log):
        self.roots=tuple(Path(r).resolve(strict=True) for r in roots)
        if not self.roots or any(not r.is_dir() for r in self.roots):raise ValueError('explicit existing directory roots required')
        self.log=Path(log)
    def resolve(self,path):
        p=Path(path)
        if not p.is_absolute():raise ValueError('absolute path required')
        q=p.resolve(strict=True)
        if not any(q.is_relative_to(r) for r in self.roots):raise PermissionError('outside allowed evidence roots')
        if any(part in DENIED_PARTS or part in DENIED_NAMES or part.startswith('.env') for part in q.parts):raise PermissionError('sensitive path not exposed')
        return q
    def record(self,kind,path,**extra):
        self.log.parent.mkdir(parents=True,exist_ok=True)
        with self.log.open('a') as f:f.write(json.dumps({'time':time.time(),'tool':kind,'path':str(path),**extra})+'\n')
    def text(self,path,start_line=1,max_lines=160):
        p=self.resolve(path)
        if not p.is_file() or p.stat().st_size>512*1024:raise ValueError('text file must be <=512KiB')
        if not 1<=start_line or not 1<=max_lines<=300:raise ValueError('invalid line window')
        lines=p.read_text(encoding='utf-8').splitlines();chunk=lines[start_line-1:start_line-1+max_lines]
        self.record('read_text',p,start_line=start_line,returned_lines=len(chunk))
        return {'path':str(p),'total_lines':len(lines),'start_line':start_line,'text':'\n'.join(chunk),'truncated':start_line-1+max_lines<len(lines),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    def listing(self,path,max_files=200):
        p=self.resolve(path)
        if not p.is_dir() or not 1<=max_files<=500:raise ValueError('directory and bound required')
        found=[]
        for child in sorted(p.rglob('*')):
            if len(found)>=max_files:break
            try:q=self.resolve(str(child))
            except (PermissionError,FileNotFoundError):continue
            if q.is_file():found.append(str(q))
        self.record('list_files',p,returned=len(found));return {'files':found,'limit':max_files}
    def search(self,path,text,max_matches=60):
        if not text or len(text)>200 or not 1<=max_matches<=100:raise ValueError('bounded literal text query required')
        rows=[]
        for file in self.listing(path,500)['files']:
            p=Path(file)
            if p.stat().st_size>512*1024:continue
            try:lines=p.read_text(encoding='utf-8').splitlines()
            except UnicodeDecodeError:continue
            for n,line in enumerate(lines,1):
                if text in line:rows.append({'path':file,'line':n,'text':line[:800]})
                if len(rows)>=max_matches:break
            if len(rows)>=max_matches:break
        self.record('search_text',path,query=text,returned=len(rows));return {'matches':rows,'limit':max_matches}
    def image(self,path):
        p=self.resolve(path)
        if not p.is_file() or p.stat().st_size>8*1024*1024:raise ValueError('image file must be <=8MiB')
        from PIL import Image as PILImage
        with PILImage.open(p) as img:
            if img.width*img.height>16_000_000:raise ValueError('image pixel bound exceeded')
            # Decode into safe PNG bytes; no path is passed back for a broader reader.
            out=io.BytesIO();img.convert('RGB').save(out,format='PNG')
        self.record('read_image',p,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        return Image(data=out.getvalue(),format='png')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',action='append',required=True);ap.add_argument('--audit',required=True);a=ap.parse_args();scope=Scope(a.root,a.audit)
    mcp=FastMCP('bounded_role_evidence',instructions='Read only explicitly supplied experiment evidence roots. No write, shell or network tools are available.',log_level='ERROR')
    ann=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    @mcp.tool(annotations=ann)
    def read_text(path:str,start_line:int=1,max_lines:int=160)->dict:
        """Read a bounded UTF-8 file window within the allowed experiment evidence roots."""
        return scope.text(path,start_line,max_lines)
    @mcp.tool(annotations=ann)
    def list_files(path:str,max_files:int=200)->dict:
        """List paths under an allowed experiment evidence directory."""
        return scope.listing(path,max_files)
    @mcp.tool(annotations=ann)
    def search_text(path:str,text:str,max_matches:int=60)->dict:
        """Search literal text in allowed evidence files; no regular expressions or shell."""
        return scope.search(path,text,max_matches)
    @mcp.tool(annotations=ann)
    def read_image(path:str)->Image:
        """Read an experiment image as PNG bytes, with the same path allowlist as text."""
        return scope.image(path)
    mcp.run(transport='stdio')

if __name__=='__main__':main()

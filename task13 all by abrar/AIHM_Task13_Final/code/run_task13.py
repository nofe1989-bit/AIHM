"""One-command rerun with Task 10, Task 11 and Task 12 source archives."""
import argparse
from pathlib import Path
import subprocess
import sys

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--task10',type=Path,required=True)
    p.add_argument('--task11',type=Path,required=True)
    p.add_argument('--task12',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('rerun_task13'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    base=Path(__file__).resolve().parent
    paths=[x.resolve() for x in (a.task10,a.task11,a.task12)]
    def call(name,*args):
        print('Running',name,flush=True)
        subprocess.run([sys.executable,str(base/name),*map(str,args)],check=True)
    call('evaluate_task13.py','--task11',paths[1],'--out',a.out/'initial')
    call('task10_replay.py','--task10',paths[0],'--task11',paths[1],'--out',a.out/'task10_replay')
    call('evaluate_shared.py','--task12',paths[2],'--task11',paths[1],'--out',a.out/'task12_shared')
    call('finalize_task13.py','--task11',paths[1],'--task10-replay',a.out/'task10_replay',
         '--task12-results',a.out/'task12_shared','--initial',a.out/'initial','--out',a.out/'final')
    print('Finished:',a.out.resolve())
if __name__=='__main__':main()

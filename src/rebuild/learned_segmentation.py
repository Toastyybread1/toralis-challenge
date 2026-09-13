"""Small 3D neural baseline with case-held-out training and partial supervision.

This is not nnU-Net. Only five proximal annotation sets are available. The
near-label negative collar is weak supervision and all other exterior voxels
are ignored during training. Development cross-validation is not a fresh test.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
import torch
from torch import nn
from torch.nn import functional as F
from src.rebuild.intensity_growth import grow,evaluate
from src.rebuild.daughter_graph import detect_daughters
from src.evaluate_predictions import compare


class SmallUNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.first=nn.Sequential(nn.Conv3d(3,8,3,padding=1),nn.ReLU(),nn.Conv3d(8,8,3,padding=1),nn.ReLU())
        self.deep=nn.Sequential(nn.Conv3d(8,16,3,padding=1),nn.ReLU(),nn.Conv3d(16,16,3,padding=1),nn.ReLU())
        self.last=nn.Sequential(nn.Conv3d(24,8,3,padding=1),nn.ReLU(),nn.Conv3d(8,1,1))
    def forward(self,x):
        skip=self.first(x);deep=self.deep(F.max_pool3d(skip,2))
        return self.last(torch.cat([skip,F.interpolate(deep,size=skip.shape[2:],mode='trilinear',align_corners=False)],dim=1))


def held_out_split(cases,held_out):
    train=[c for c in cases if c!=held_out]
    if held_out not in cases or not train:raise ValueError('Invalid held-out split')
    return train


def prepare(case):
    folder=Path('references/border_results')/f'case_{case}'/'inputs'
    ct=sitk.ReadImage(str(folder/f'orig{case}.nii.gz'));parent=sitk.ReadImage(str(folder/f'aorta{case}.nii.gz'))
    data=grow(ct,parent,0,.5,radius_mm=25)
    target=sitk.GetArrayFromImage(sitk.ReadImage(str(folder/f'daughters{case}_draft.nii.gz')))[data['box']]
    x=np.stack([np.clip(data['ct'],-200,800)/500.,data['parent'].astype(float),np.clip(data['distance'],0,25)/25]).astype(np.float32)
    positive=target>0
    near=ndi.distance_transform_edt(~positive,sampling=np.array(ct.GetSpacing())[::-1])<=3.
    # Finite proximal annotations are not exhaustive full-scan negatives.
    supervised=near|data['parent']
    return {'data':data,'x':x,'target':target,'supervised':supervised,'positive':np.argwhere(positive),
            'negative':np.argwhere(supervised&~positive),
            'annotations':json.loads((folder/'annotations.json').read_text())}


def patch(sample,rng,size=24):
    points=sample['positive'] if rng.random()<.5 else sample['negative']
    centre=points[rng.integers(len(points))]+rng.integers(-3,4,size=3)
    lo=np.clip(centre-size//2,0,np.maximum(0,np.array(sample['target'].shape)-size))
    box=tuple(slice(int(v),int(v)+size) for v in lo)
    x=sample['x'][(slice(None),)+box];y=(sample['target'][box]>0).astype(np.float32);m=sample['supervised'][box].astype(np.float32)
    pads=[(0,max(0,size-n)) for n in y.shape]
    x=np.pad(x,[(0,0)]+pads);y=np.pad(y,pads);m=np.pad(m,pads)
    for axis in range(3):
        if rng.random()<.5:x=np.flip(x,axis+1);y=np.flip(y,axis);m=np.flip(m,axis)
    return x.copy(),y[None].copy(),m[None].copy()


def masked_loss(logits,target,mask):
    bce=F.binary_cross_entropy_with_logits(logits,target,reduction='none')
    bce=(bce*mask*(1+3*target)).sum()/mask.sum().clamp_min(1)
    probability=logits.sigmoid()*mask
    dice=1-(2*(probability*target).sum()+1)/(probability.sum()+(target*mask).sum()+1)
    return bce+dice


def predict(model,x,device):
    # Z slabs with halo limit peak memory and cover arbitrary image dimensions.
    output=np.zeros(x.shape[1:],np.float32)
    with torch.no_grad():
        for start in range(0,x.shape[1],24):
            end=min(start+24,x.shape[1]);lo=max(0,start-16);hi=min(x.shape[1],end+16)
            tensor=torch.from_numpy(x[:,lo:hi].copy())[None].to(device)
            scores=model(tensor).sigmoid()[0,0].cpu().numpy()
            output[start:end]=scores[start-lo:end-lo]
    return output


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--steps',type=int,default=200)
    parser.add_argument('--output',type=Path,default=Path('models/learned_results'))
    args=parser.parse_args();torch.set_num_threads(4)
    device='cuda' if torch.cuda.is_available() else 'cpu'
    root=args.output;root.mkdir(parents=True,exist_ok=True)
    cases=list(range(19,24));samples={c:prepare(c) for c in cases};rows=[]
    for held in cases:
        train=held_out_split(cases,held);rng=np.random.default_rng(8100+held);torch.manual_seed(8100+held)
        model=SmallUNet().to(device);optimizer=torch.optim.Adam(model.parameters(),lr=.001);model.train();losses=[]
        start=time.perf_counter()
        for step in range(args.steps):
            batch=[patch(samples[train[rng.integers(len(train))]],rng) for _ in range(4)]
            x,y,m=[torch.from_numpy(np.stack([b[i] for b in batch])).to(device) for i in range(3)]
            optimizer.zero_grad();loss=masked_loss(model(x),y,m);loss.backward();optimizer.step();losses.append(float(loss.detach()))
            if (step+1)%max(50,args.steps//4)==0:print(f'held={held} step={step+1} loss={losses[-1]:.4f}',flush=True)
        model.eval();seconds=time.perf_counter()-start
        out=root/f'held_out_{held}';out.mkdir(exist_ok=True)
        (out/'training_loss.json').write_text(json.dumps(losses))
        torch.save({'state_dict':model.cpu().state_dict(),'training_cases':train,'held_out_case':held,
            'steps':args.steps,'input_channels':['HU_clipped_div500','parent','distance_div25']},out/'model.pt')
        model.to(device);s=samples[held];start=time.perf_counter();probability=predict(model,s['x'],device);prediction_seconds=time.perf_counter()-start
        data=s['data'];p=data['parent'];domain=(data['distance']<=15)&(probability>=.5)
        expanded=ndi.binary_propagation(p,structure=ndi.generate_binary_structure(3,1),mask=p|domain)
        added=expanded&~p
        learned=detect_daughters({**data,'added':added})
        for name,array in [('probability',probability),('growth',added.astype(np.uint8))]:
            im=sitk.GetImageFromArray(array);im.CopyInformation(data['roi']);sitk.WriteImage(im,str(out/f'{name}.nii.gz'))
        (out/'daughters.json').write_text(json.dumps({k:v for k,v in learned.items() if k!='graphs'},indent=2))
        target=s['target']>0;region=s['supervised']&~p
        tp=int(np.count_nonzero(added&target));fp=int(np.count_nonzero(added&~target&region));fn=int(np.count_nonzero(~added&target))
        row={'held_out_case':held,'training_cases':train,'device':device,'training_seconds':seconds,'prediction_seconds':prediction_seconds,
             'first_loss':losses[0],'last_loss':losses[-1],'steps':args.steps,
             'reference_coverage':tp/int(target.sum()),'local_annotation_dice':2*tp/(2*tp+fp+fn),
             'local_dice_warning':'Weak near-label negative collar; not full-volume precision.',
             'evaluation':evaluate(added,s['target'],data['roi'].GetSpacing(),data['distance']),
             'origin_evaluation_3mm':compare(learned,s['annotations'],3.),'graph_status_counts':learned['status_counts']}
        if held==19:
            model.cpu();start=time.perf_counter();cpu_probability=predict(model,s['x'],'cpu');row['cpu_prediction_seconds']=time.perf_counter()-start
            row['cpu_gpu_max_difference']=float(np.max(np.abs(cpu_probability-probability)))
        rows.append(row);(root/'summary.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
    (root/'training_manifest.json').write_text(json.dumps({'cases':cases,'folds':[{'held_out':r['held_out_case'],'train':r['training_cases']} for r in rows],
        'seed':8100,'torch_version':torch.__version__,'label_status':'Organizer proximal draft labels; near-label background is weak supervision',
        'evaluation_status':'Development leave-one-case-out. Cases previously inspected and used for classical tuning; not an untouched test.'},indent=2))

if __name__=='__main__':main()

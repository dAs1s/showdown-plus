"""Extract editable PNG cells or assemble them back into transparent atlases."""
import argparse
import json
from pathlib import Path
from PIL import Image

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("operation", choices=["split","pack"])
    cli.add_argument("assets", type=Path, help="Folder containing surf-timing.json and the six atlases")
    cli.add_argument("frames", type=Path, help="Folder of individual RGBA frames")
    cli.add_argument("--output", type=Path, help="New output folder for packed assets")
    args = cli.parse_args()
    if args.operation=="pack" and args.output is None:
        cli.error("pack requires --output")
    manifest_path = args.assets/"surf-timing.json"
    info = json.loads(manifest_path.read_text())
    w,h = (info["spriteFrame"][key] for key in ("width","height"))
    cols,rows = (info["atlas"][key] for key in ("columns","rows"))
    names = [name for side in ("playerAttack","opponentAttack") for name in info[side].values()]
    if args.operation=="pack":
        args.output.mkdir(parents=True,exist_ok=True)
    for name in names:
        folder = args.frames/Path(name).stem
        if args.operation=="split":
            folder.mkdir(parents=True,exist_ok=True)
            atlas = Image.open(args.assets/name).convert("RGBA")
        else:
            atlas = Image.new("RGBA",(cols*w,rows*h))
        for index in range(info["frameCount"]):
            x,y = index%cols*w,index//cols*h
            path = folder/f"{index:03d}.png"
            if args.operation=="split":
                atlas.crop((x,y,x+w,y+h)).save(path)
            else:
                with Image.open(path) as cell:
                    if cell.size!=(w,h) or cell.mode!="RGBA":
                        raise ValueError(f"Expected {w}x{h} RGBA at {path}")
                    atlas.paste(cell,(x,y))
        if args.operation=="pack":
            atlas.save(args.output/name)
    if args.operation=="pack":
        (args.output/manifest_path.name).write_bytes(manifest_path.read_bytes())

if __name__=="__main__":
    main()

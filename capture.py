"""PH70 acquisition with explicitly negotiated edge-preserving TWAIN settings."""
import argparse
import json
import time
from pathlib import Path
from PIL import Image
import twain
from twain.lowlevel import constants as c
import backend


def feeder_loaded(source):
    try:
        _, value = source.get_capability_current(c.CAP_FEEDERLOADED)
        return bool(value)
    except Exception as exc:
        raise RuntimeError('Scan mode requires feeder paper detection. Use single-batch scanning with this driver.') from exc


def capture_batches(source, before, after, continuous, stopped, state, pause=time.sleep):
    """Keep all TWAIN calls on the acquisition thread and finish duplex batches.

    Stop requests are checked between acquisitions, never between duplex sides.
    Driver faults propagate instead of triggering an unattended retry loop.
    """
    batches = 0
    while not stopped():
        if continuous:
            state('waiting')
            while not stopped() and not feeder_loaded(source):
                pause(.25)
            if stopped(): break
        state('scanning')
        source.acquire_natively(after,before,show_ui=False,modal=False)
        batches += 1
        if not continuous: break
        pause(.25) # Avoid a tight re-enable loop if the sensor is slow to settle.
    state('finished')
    return batches


def configure(source, dpi, duplex, color, size):
    def set_value(name, value, required=True):
        cap = getattr(c, name)
        try:
            kind, previous = source.get_capability_current(cap)
            source.set_capability(cap, kind, value)
            _, actual = source.get_capability_current(cap)
            if actual != value:
                raise RuntimeError(f'{name}: requested {value}, driver returned {actual}')
            return actual
        except Exception:
            if required: raise
            return None
    set_value('CAP_FEEDERENABLED', True)
    set_value('CAP_DUPLEXENABLED', duplex)
    set_value('ICAP_UNITS', c.TWUN_INCHES)
    set_value('ICAP_PIXELTYPE', {'color':c.TWPT_RGB,'gray':c.TWPT_GRAY,'bw':c.TWPT_BW}[color])
    set_value('ICAP_XRESOLUTION', dpi)
    set_value('ICAP_YRESOLUTION', dpi)
    widths = {'letter':(8.5,11),'legal':(8.5,14),'a4':(210/25.4,297/25.4),
              '4x6in':(4,6),'5x7in':(5,7),'8x10in':(8,10)}
    width,height = widths[size]
    _, maximum = source.get_capability_current(c.ICAP_PHYSICALWIDTH)
    # Feeders center the originals; keep requested smaller scan regions centered.
    offset = max(0,(maximum-width)/2)
    source.set_image_layout((offset,0,offset+width,height))
    # Apply these LAST: page-size and resolution changes can reset driver options.
    set_value('ICAP_AUTOMATICBORDERDETECTION', False)
    set_value('ICAP_AUTOMATICDESKEW', False)
    set_value('ICAP_AUTOMATICROTATE', False, required=False)
    set_value('ICAP_OVERSCAN', c.TWOV_ALL)
    set_value('CAP_XFERCOUNT', -1, required=False)
    set_value('CAP_INDICATORS', False, required=False)
    return {'automatic_crop':False, 'driver_deskew':False, 'overscan':'all sides',
            'dpi':dpi, 'duplex':duplex, 'layout':source.get_image_layout()[0]}


def run(argv):
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',required=True)
    parser.add_argument('--device',required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--dpi',type=int,required=True)
    parser.add_argument('--size',required=True)
    parser.add_argument('--color',required=True)
    parser.add_argument('--inspect',action='store_true')
    parser.add_argument('--continuous',action='store_true')
    args=parser.parse_args(argv)
    folder=Path(args.folder); folder.mkdir(parents=True,exist_ok=True)
    count=0
    metadata={}
    started=time.perf_counter()
    metrics={'pages':0,'bitmap_write_seconds':0.0,'batches':0}
    def state(value):
        temporary=folder/'capture-state.tmp'
        temporary.write_text(json.dumps({'state':value,'pages':count}),encoding='utf-8')
        temporary.replace(folder/'capture-state.json')
    try:
        dsm=backend.engine().parent/'lib'/'_win64'/'twaindsm.dll'
        with twain.SourceManager(dsm_name=str(dsm),ProductName='Duplex Scan') as manager:
            with manager.open_source(args.device) as source:
                metrics['driver_open_seconds']=time.perf_counter()-started
                setup_started=time.perf_counter()
                report=configure(source,args.dpi,args.source=='duplex',args.color,args.size)
                metrics['configure_seconds']=time.perf_counter()-setup_started
                (folder/'capture-settings.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                if args.inspect:
                    report['feeder_loaded']=feeder_loaded(source)
                    print(json.dumps(report),flush=True)
                    return 0
                def before(info):
                    metadata.clear(); metadata.update(info)
                def after(image, more):
                    nonlocal count
                    count+=1
                    temporary=folder/f'.page-{count:04d}.partial.bmp'
                    destination=folder/f'page-{count:04d}.bmp'
                    write_started=time.perf_counter()
                    try:
                        image.save(str(temporary))
                        temporary.replace(destination)
                        metrics['pages']=count
                        metrics['bitmap_write_seconds']+=time.perf_counter()-write_started
                    finally:
                        temporary.unlink(missing_ok=True)
                    print(f'Captured page {count}',flush=True)
                metrics['batches']=capture_batches(source,before,after,args.continuous,
                    lambda:(folder/'stop-request').exists(),state)
        return 0
    except Exception as exc:
        (folder/'capture-error.txt').write_text(f'{type(exc).__name__}: {exc}',encoding='utf-8')
        print(f'{type(exc).__name__}: {exc}',flush=True)
        return 1
    finally:
        metrics['session_seconds']=time.perf_counter()-started
        try: (folder/'capture-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
        except OSError: pass

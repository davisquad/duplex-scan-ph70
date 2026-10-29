"""Native Focus workspace: preview first, compact finishing, batch below."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


def system_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
    except (ImportError, OSError):
        return False


def apply_theme(app):
    root = app.root
    choice = app.appearance.get()
    dark = choice == 'Dark' or (choice == 'System' and system_dark())
    p = app.palette = ({'bg':'#171b22','panel':'#202630','text':'#edf2fa','muted':'#a4b0c3',
                        'line':'#343e4d','stage':'#12171e','selected':'#263954','shadow':'#080c12'} if dark else
                       {'bg':'#f6f7f9','panel':'#ffffff','text':'#172238','muted':'#647087',
                        'line':'#e3e7ee','stage':'#e9edf2','selected':'#edf3ff','shadow':'#cbd3df'})
    p['accent'] = '#356be6'
    root.configure(bg=p['bg'])
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.',font=('Segoe UI',10),background=p['bg'],foreground=p['text'])
    style.configure('TFrame',background=p['bg'])
    style.configure('Panel.TFrame',background=p['panel'])
    style.configure('TLabel',background=p['bg'],foreground=p['text'])
    style.configure('Panel.TLabel',background=p['panel'])
    style.configure('Title.TLabel',font=('Segoe UI Semibold',21))
    style.configure('Brand.TLabel',font=('Segoe UI Semibold',15),background=p['panel'])
    style.configure('Small.TLabel',font=('Segoe UI',9),foreground=p['muted'])
    style.configure('Panel.Small.TLabel',font=('Segoe UI',9),foreground=p['muted'],background=p['panel'])
    style.configure('Section.TLabel',font=('Segoe UI Semibold',10),background=p['panel'])
    style.configure('TButton',padding=(12,8),background=p['panel'],foreground=p['text'],
                    bordercolor=p['line'],lightcolor=p['panel'],darkcolor=p['panel'],relief='flat')
    style.map('TButton',background=[('active',p['selected']),('disabled',p['bg'])],foreground=[('disabled',p['muted'])])
    style.configure('Primary.TButton',background=p['accent'],foreground='white',bordercolor=p['accent'],font=('Segoe UI Semibold',10))
    style.map('Primary.TButton',background=[('disabled',p['line']),('active','#2857c0')],foreground=[('disabled',p['muted']),('active','white')])
    style.configure('Quiet.TButton',padding=(8,5),borderwidth=0)
    style.configure('TCheckbutton',background=p['panel'],foreground=p['text'],padding=(0,4))
    style.map('TCheckbutton',background=[('active',p['panel'])],indicatorcolor=[('selected',p['accent'])])
    style.configure('TCombobox',fieldbackground=p['panel'],background=p['panel'],foreground=p['text'],padding=5,arrowsize=14)
    style.map('TCombobox',fieldbackground=[('readonly',p['panel'])],foreground=[('readonly',p['text'])])
    style.configure('TSpinbox',fieldbackground=p['panel'],foreground=p['text'],background=p['panel'],padding=4)
    style.configure('TSeparator',background=p['line'])
    root.option_add('*TCombobox*Listbox.background',p['panel'])
    root.option_add('*TCombobox*Listbox.foreground',p['text'])
    if hasattr(app, 'canvas'):
        app.canvas.configure(bg=p['stage'])
        app.grid_canvas.configure(bg=p['bg'])
        app.draw_grid()
        app.schedule_preview()
    for name in ('settings_window', 'edits_window'):
        if hasattr(app, name): getattr(app, name).configure(bg=p['bg'])


def build_focus_ui(app):
    root = app.root
    root.title('Duplex Scan 1.10.0 • Focus workspace')
    root.geometry('1180x800')
    root.minsize(960,720)
    app.appearance = tk.StringVar(value=app.cfg.get('appearance', 'Light'))
    apply_theme(app)
    p = app.palette
    app.connection = tk.StringVar(value='○  Looking for scanner')
    app.current_label = tk.StringVar(value='No scan selected')
    app.batch_subtitle = tk.StringVar(value='Load your cards to start a new batch')
    app.page_controls = []

    chrome = ttk.Frame(root,style='Panel.TFrame',padding=(24,12))
    chrome.pack(fill='x')
    icon = Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'DuplexScan-Neon.png'
    if icon.exists():
        with Image.open(icon) as source:
            app.brand_icon = ImageTk.PhotoImage(source.resize((30,30),Image.Resampling.LANCZOS))
        ttk.Label(chrome,image=app.brand_icon,style='Panel.TLabel').pack(side='left',padx=(0,10))
    ttk.Label(chrome,text='Duplex Scan',style='Brand.TLabel').pack(side='left')
    appearance = app.combo(chrome,app.appearance,['Light','Dark','System'],side='right',width=8)
    appearance.bind('<<ComboboxSelected>>',lambda e:apply_theme(app))
    ttk.Label(chrome,text='Appearance',style='Panel.Small.TLabel').pack(side='right',padx=(18,8))
    ttk.Label(chrome,textvariable=app.connection,style='Panel.Small.TLabel').pack(side='right')
    ttk.Separator(root).pack(fill='x')

    # Pack the footer first so it remains visible when the window gets shorter.
    footer = ttk.Frame(root,padding=(24,10))
    footer.pack(side='bottom',fill='x')
    app.progress = ttk.Progressbar(footer,mode='indeterminate',length=60)
    app.progress.pack(side='left',padx=(0,12))
    ttk.Label(footer,textvariable=app.status,style='Small.TLabel',wraplength=760).pack(side='left')
    app.stop_button = ttk.Button(footer,text='Stop scan',command=app.stop,state='disabled',style='Quiet.TButton')
    app.stop_button.pack(side='right')
    head = ttk.Frame(root,padding=(24,20,24,18));head.pack(fill='x')
    titles = ttk.Frame(head);titles.pack(side='left')
    ttk.Label(titles,text='Review your scans',style='Title.TLabel').pack(anchor='w')
    ttk.Label(titles,textvariable=app.batch_subtitle,style='Small.TLabel').pack(anchor='w',pady=(4,0))
    app.save_button = app.button(head,'Save JPEGs',app.save,side='right',style='Primary.TButton')
    app.scan_button = app.button(head,'Scan pages',app.scan,side='right',padx=(0,8))
    app.button(head,'Import',app.import_images,side='right',padx=(0,8),style='Quiet.TButton')

    body = ttk.Frame(root,padding=(24,0,24,8));body.pack(fill='both',expand=True)
    inspector = ttk.Frame(body,width=252,style='Panel.TFrame',padding=18)
    inspector.pack(side='right',fill='y',padx=(18,0));inspector.pack_propagate(False)
    review = ttk.Frame(body);review.pack(side='left',fill='both',expand=True)

    # Compact inspector; uncommon capture options have their own dialog.
    def caption(text):
        ttk.Label(inspector,text=text,style='Section.TLabel').pack(anchor='w',pady=(0,10))
    caption('CAPTURE')
    row=ttk.Frame(inspector,style='Panel.TFrame');row.pack(fill='x')
    ttk.Label(row,text='Resolution',style='Panel.TLabel').pack(side='left')
    app.combo(row,app.dpi,['200','300','400','600'],side='right',width=6)
    row=ttk.Frame(inspector,style='Panel.TFrame');row.pack(fill='x',pady=4)
    ttk.Label(row,text='Sides',style='Panel.TLabel').pack(side='left')
    app.combo(row,app.source,['Both sides (duplex)','Front side only'],side='right',width=17)
    app.button(inspector,'Scanner settings…',lambda:show_settings(app),fill='x',pady=(8,4),style='Quiet.TButton')
    ttk.Separator(inspector).pack(fill='x',pady=16)
    caption('FINISHING')
    for text,var in [('Auto crop',app.autocrop),('Straighten',app.deskew)]:
        widget=ttk.Checkbutton(inspector,text=text,variable=var,command=app.changed)
        widget.pack(anchor='w');app.controls.append(widget)
    row=ttk.Frame(inspector,style='Panel.TFrame');row.pack(fill='x',pady=(12,6))
    ttk.Label(row,text='Edge space',style='Panel.TLabel').pack(side='left')
    ttk.Label(row,text='mm',style='Panel.Small.TLabel').pack(side='right')
    spin=ttk.Spinbox(row,from_=0,to=25,increment=.1,textvariable=app.margin,width=5,command=app.changed)
    spin.pack(side='right',padx=6);app.controls.append(spin)
    spin.bind('<Return>',lambda e:app.changed());spin.bind('<FocusOut>',lambda e:app.changed())
    ttk.Label(inspector,text='Keeps real scanned background\naround the card.',style='Panel.Small.TLabel',wraplength=210).pack(anchor='w',pady=(2,0))
    ttk.Separator(inspector).pack(fill='x',pady=16)
    ttk.Label(inspector,text='Save location',style='Panel.Small.TLabel').pack(anchor='w')
    ttk.Label(inspector,text='Pictures / Scanned Photos',style='Panel.TLabel',wraplength=210).pack(anchor='w',pady=5)
    ttk.Label(inspector,text='JPEG · Full color detail\nBatch clears after saving.',style='Panel.Small.TLabel').pack(anchor='w')
    app.button(inspector,'New batch',app.new_batch,fill='x',pady=(18,0),style='Quiet.TButton')

    # The gallery is reserved at the bottom; remaining height belongs to preview.
    gallery_section=ttk.Frame(review);gallery_section.pack(side='bottom',fill='x',pady=(14,0))
    row=ttk.Frame(gallery_section);row.pack(fill='x',pady=(0,8))
    ttk.Label(row,text='Current batch',font=('Segoe UI Semibold',10)).pack(side='left')
    ttk.Label(row,textvariable=app.count,style='Small.TLabel').pack(side='right')
    gallery=ttk.Frame(gallery_section);gallery.pack(fill='x')
    app.grid_canvas=tk.Canvas(gallery,height=150,bg=p['bg'],highlightthickness=0)
    app.grid_canvas.pack(side='left',fill='x',expand=True)
    scrollbar=ttk.Scrollbar(gallery,command=app.grid_canvas.yview);scrollbar.pack(side='right',fill='y')
    app.grid_canvas.configure(yscrollcommand=scrollbar.set)
    app.grid_canvas.bind('<Configure>',lambda e:app.draw_grid())
    app.grid_canvas.bind('<Button-1>',app.grid_select)
    app.grid_canvas.bind('<MouseWheel>',lambda e:app.grid_canvas.yview_scroll(-int(e.delta/120),'units'))
    app.listbox=tk.Listbox(review,exportselection=False) # Selection model, represented by thumbnails.
    panel=ttk.Frame(review,style='Panel.TFrame',padding=1);panel.pack(fill='both',expand=True)
    row=ttk.Frame(panel,style='Panel.TFrame',padding=(14,8));row.pack(fill='x')
    ttk.Label(row,textvariable=app.current_label,style='Section.TLabel').pack(side='left')
    ttk.Label(row,text='Fit to view',style='Panel.Small.TLabel').pack(side='right')
    tools=ttk.Frame(panel,style='Panel.TFrame',padding=(10,6));tools.pack(side='bottom',fill='x')
    app.page_controls.append(app.button(tools,'↶ Rotate',lambda:app.rotate(-90),side='left',style='Quiet.TButton'))
    original=ttk.Checkbutton(tools,text='Original / crop',variable=app.original,command=app.schedule_preview)
    original.pack(side='left',padx=8);app.controls.append(original);app.page_controls.append(original)
    app.page_controls.append(app.button(tools,'Page edits…',lambda:show_page_edits(app),side='right',style='Quiet.TButton'))
    app.canvas=tk.Canvas(panel,bg=p['stage'],highlightthickness=0)
    app.canvas.pack(fill='both',expand=True)
    app.canvas.bind('<Configure>',lambda e:app.schedule_preview())
    app.canvas.bind('<ButtonPress-1>',app.crop_begin)
    app.canvas.bind('<B1-Motion>',app.crop_drag)
    app.canvas.bind('<ButtonRelease-1>',app.crop_end)
    # Create settings once so device discovery has a stable destination.
    create_settings(app)
    app.mode.trace_add('write',lambda *a:app.changed())
    app.update_review_controls()


def dialog(app,title):
    window=tk.Toplevel(app.root)
    window.withdraw();window.title(title);window.transient(app.root);window.resizable(False,False)
    window.configure(bg=app.palette['bg'])
    window.protocol('WM_DELETE_WINDOW',window.withdraw)
    pane=ttk.Frame(window,padding=24);pane.pack(fill='both',expand=True)
    return window,pane


def create_settings(app):
    window,pane=dialog(app,'Scanner settings')
    app.settings_window=window
    ttk.Label(pane,text='Scanner settings',style='Title.TLabel').pack(anchor='w',pady=(0,18))
    app.device_combo=app.label_combo(pane,'Scanner',app.device,[])
    row=ttk.Frame(pane);row.pack(fill='x',pady=8)
    app.combo(row,app.driver,['twain','wia'],side='left',width=10)
    app.button(row,'Refresh',app.refresh,side='right')
    app.label_combo(pane,'Paper size',app.size,['Letter','A4','Legal','4 × 6 in','5 × 7 in','8 × 10 in'])
    app.label_combo(pane,'Color',app.color,['Color','Grayscale','Black & white'])
    app.label_combo(pane,'Crop detection',app.mode,['Card outline','Content + space'])
    widget=ttk.Checkbutton(pane,text='Rotate new scans 180°',variable=app.scan_flip)
    widget.pack(anchor='w',pady=12);app.controls.append(widget)
    ttk.Label(pane,text='Capture keeps a wide surround. Finishing applies\nthe final crop without adding a white border.',style='Small.TLabel').pack(anchor='w',pady=(4,16))
    ttk.Button(pane,text='Done',command=window.withdraw,style='Primary.TButton').pack(anchor='e')


def show_settings(app):
    app.settings_window.deiconify();app.settings_window.lift()


def show_page_edits(app):
    if not hasattr(app,'edits_window'):
        window,pane=dialog(app,'Page edits');app.edits_window=window
        ttk.Label(pane,text='Page edits',style='Title.TLabel').pack(anchor='w',pady=(0,16))
        row=ttk.Frame(pane);row.pack(fill='x')
        for label,action in [('Rotate 90°',lambda:app.rotate(90)),('Rotate 180°',lambda:app.rotate(180))]:
            app.page_controls.append(app.button(row,label,action,side='left',padx=(0,8)))
        row=ttk.Frame(pane);row.pack(fill='x',pady=14)
        ttk.Label(row,text='Fine tilt (degrees)').pack(side='left')
        spin=ttk.Spinbox(row,from_=-15,to=15,increment=.2,width=6,textvariable=app.tilt,command=app.set_tilt)
        spin.pack(side='right');app.controls.append(spin);app.page_controls.append(spin)
        spin.bind('<Return>',lambda e:app.set_tilt());spin.bind('<FocusOut>',lambda e:app.set_tilt())
        row=ttk.Frame(pane);row.pack(fill='x',pady=6)
        for label,action in [('Move earlier',lambda:app.move(-1)),('Move later',lambda:app.move(1)),('Remove',app.remove)]:
            app.page_controls.append(app.button(row,label,action,side='left',padx=(0,6)))
        app.page_controls.append(app.button(pane,'Reset page edits',app.reset_page,fill='x',pady=(12,8)))
        ttk.Label(pane,textvariable=app.details,style='Small.TLabel',wraplength=380).pack(anchor='w',pady=(4,16))
        ttk.Button(pane,text='Done',command=window.withdraw,style='Primary.TButton').pack(anchor='e')
    app.update_review_controls()
    app.edits_window.deiconify();app.edits_window.lift()

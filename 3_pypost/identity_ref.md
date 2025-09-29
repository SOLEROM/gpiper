#

* on hailo tappas i seen a way to move data from the pipe to python post;

```

PIPELINE_TMPL = r"""
hailomuxer name=hmux

...
  identity name=identity_callback signal-handoffs=true !
....



def on_handoff(identity, buffer):
    ...
    ...
    ...


def main():

    desc = PIPELINE_TMPL.format(device=args.device, hef=args.hef, post_so=args.post_so)
    pipeline = Gst.parse_launch(desc)

    # Wire handoff 
    identity = pipeline.get_by_name("identity_callback")
    identity.connect("handoff", on_handoff)



```
# appsink

for cases to pull frames rather than be called on a streaming thread

os side
``` c
... ! appsink name=grabber emit-signals=true sync=false max-buffers=1 drop=true
```

python

``` python
grabber = pipeline.get_by_name("grabber")
grabber.connect("new-sample", on_sample)

def on_sample(sink):
    sample = sink.emit("pull-sample")
    buffer = sample.get_buffer()
    # map buffer, read bytes or meta
    sample.unref()
    return Gst.FlowReturn.OK

```
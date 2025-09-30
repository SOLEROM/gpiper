# using idenity

 "fast conveyor belt (the GStreamer pipeline) that hands your Python code a box (a Gst.Buffer) every time a frame goes by—and you attached a bell to the belt so you can grab the box for a peek."


```
gst-inspect-1.0 identity   
Factory Details:
  Rank                     none (0)
  Long-name                Identity
  Klass                    Generic
  Description              Pass data without modification
  Author                   Erik Walthinsen <omega@cse.ogi.edu>


Plugin Details:
  Name                     coreelements
  Description              GStreamer core elements
  Filename                 /usr/lib/x86_64-linux-gnu/gstreamer-1.0/libgstcoreelements.so
  Version                  1.16.3
  License                  LGPL
  Source module            gstreamer
  Source release date      2020-10-21
  Binary package           GStreamer (Ubuntu)
  Origin URL               https://launchpad.net/distros/ubuntu/+source/gstreamer1.0

GObject
 +----GInitiallyUnowned
       +----GstObject
             +----GstElement
                   +----GstBaseTransform


```

identity lives in the Core Plugins under the plugin called coreelements (the same family that ships queue, fakesink, filesrc, etc.).

called the identity transform—like the math function f(x)=x. It forwards each buffer unchanged, but offers handy debug knobs.


## (1)  create chain

create a chain of C objects pushing Gst.Buffer objects from source → sink. Every buffer is a chunk of memory + timestamps + optional metadata. 


```
desc = PIPELINE_TMPL.format(...)
pipeline = Gst.parse_launch(desc)
```

* Creates elements (v4l2src, videorate, videoscale, videoconvert, hailonet, hailofilter, hailotracker, identity, hailooverlay, fpsdisplaysink, etc.).
* Links pads left-to-right (sometimes requesting dynamic pads under the hood).
* Configures caps filters like video/x-raw,format=UYVY,... (this is how elements agree on the exact bytes per frame: format, width, height, framerate).
* Spawns threads where you add queues. Each queue is a new streaming thread and a small ring buffer.


## (2) use idenity

identity is a pass-through element (it forwards buffers verbatim). When signal-handoffs=true, it emits a signal for each buffer it forwards. That signal is how Python gets called for every frame.

* The streaming thread inside identity emits "handoff"

* your callback runs in that streaming thread. Don’t do heavy/blocking work here or you’ll stall the pipeline.

* copy what you need and hand it to a worker thread/queue.

* What is passed? The current Gst.Buffer (and the element/pad).


## (3) Gst.Buffer

Gst.Buffer contains:

* Memory spans (one or more Gst.Memory blocks) holding the actual bytes (image planes, encoded bitstream, etc.).

* Timestamps: buffer.pts, buffer.dts, buffer.duration (nanoseconds; Gst.CLOCK_TIME_NONE if unknown).

* Metadata list: a list of GstMeta items attached by elements.

## (4) BUS messages

```
bus.connect("message", on_msg))
```

this is a control-plane, low frequency second channel passing to python.

Elements post messages (ERROR/EOS/STATE changes, and custom ELEMENT structs like fpsdisplaysink stats). GLib delivers them in the main loop thread.
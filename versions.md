# check versions


```
> gst-launch-1.0 --version
gst-launch-1.0 version 1.16.3
```

```
> dpkg -l | grep gstreamer1.0
ii  gstreamer1.0-alsa:amd64                       1.16.3-0ubuntu1.4                             amd64        GStreamer plugin for ALSA
ii  gstreamer1.0-clutter-3.0:amd64                3.0.27-1                                      amd64        Clutter PLugin for GStreamer 1.0
ii  gstreamer1.0-gl:amd64                         1.16.3-0ubuntu1.4                             amd64        GStreamer plugins for GL
ii  gstreamer1.0-gtk3:amd64                       1.16.3-0ubuntu1.3                             amd64        GStreamer plugin for GTK+3
ii  gstreamer1.0-libav:amd64                      1.16.2-2                                      amd64        ffmpeg plugin for GStreamer
ii  gstreamer1.0-packagekit                       1.1.13-2ubuntu1.1                             amd64        GStreamer plugin to install codecs using PackageKit
ii  gstreamer1.0-plugins-bad:amd64                1.16.3-0ubuntu1.1                             amd64        GStreamer plugins from the "bad" set
ii  gstreamer1.0-plugins-base:amd64               1.16.3-0ubuntu1.4                             amd64        GStreamer plugins from the "base" set
ii  gstreamer1.0-plugins-base-apps                1.16.3-0ubuntu1.4                             amd64        GStreamer helper programs from the "base" set
ii  gstreamer1.0-plugins-good:amd64               1.16.3-0ubuntu1.3                             amd64        GStreamer plugins from the "good" set
ii  gstreamer1.0-plugins-rtp                      1.14.4.1                                      amd64        GStreamer elements from the "rtp" set
ii  gstreamer1.0-plugins-ugly:amd64               1.16.2-2build1                                amd64        GStreamer plugins from the "ugly" set
ii  gstreamer1.0-pulseaudio:amd64                 1.16.3-0ubuntu1.3                             amd64        GStreamer plugin for PulseAudio
ii  gstreamer1.0-tools                            1.16.3-0ubuntu1.2                             amd64        Tools for use with GStreamer
ii  gstreamer1.0-vaapi:amd64                      1.16.2-2                                      amd64        VA-API plugins for GStreamer
ii  gstreamer1.0-x:amd64                          1.16.3-0ubuntu1.4                             amd64        GStreamer plugins for X11 and Pango
ii  libgstreamer1.0-0:amd64                       1.16.3-0ubuntu1.2                             amd64        Core GStreamer libraries and elements

```


## upgrade

* use isolated envs
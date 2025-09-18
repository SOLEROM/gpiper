# demo files

* test30sec avi from the web

* test30sec mp4 converted with ffmpeg
```
ffmpeg -i test30sec.avi -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k test30sec.mp4
```

* trimed to 2 seconds with ffmpeg
```
ffmpeg -i test30sec.mp4 -t 2 -c copy test2sec.mp4
```
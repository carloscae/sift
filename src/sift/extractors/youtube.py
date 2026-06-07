from sift.extractors.ytdlp_base import YtDlpAudioExtractor


class YouTubeExtractor(YtDlpAudioExtractor):
    platform = "youtube"
    _HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

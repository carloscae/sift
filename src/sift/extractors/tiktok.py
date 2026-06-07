from sift.extractors.ytdlp_base import YtDlpAudioExtractor


class TikTokExtractor(YtDlpAudioExtractor):
    platform = "tiktok"
    _HOSTS = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}

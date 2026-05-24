from sift.extractors.base import register_extractor
from sift.extractors.generic_url import GenericUrlExtractor
from sift.extractors.tiktok import TikTokExtractor
from sift.extractors.twitter import TwitterExtractor
from sift.extractors.youtube import YouTubeExtractor


def _register_builtins() -> None:
    register_extractor(TikTokExtractor())
    register_extractor(YouTubeExtractor())
    register_extractor(TwitterExtractor())
    register_extractor(GenericUrlExtractor())


_register_builtins()

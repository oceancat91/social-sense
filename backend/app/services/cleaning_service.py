"""数据清洗服务：去噪、标准化、去重"""
import hashlib
import re


class CleaningService:
    """社交媒体文本清洗管道"""

    URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')
    HTML_PATTERN = re.compile(r'<[^>]+>')
    MENTION_PATTERN = re.compile(r'@[\w一-龥\-]+\s*')
    TOPIC_PATTERN = re.compile(r'#([^#]+)#')   # 微博话题 #xxx#
    WHITESPACE_PATTERN = re.compile(r'\s+')
    REPLY_PATTERN = re.compile(r'^回复\s*@[\w一-龥\-]+\s*[:：]?\s*')

    MIN_CONTENT_LENGTH = 5

    @classmethod
    def clean_text(cls, text: str, keep_topic: bool = True) -> str:
        """清洗单条文本：去 HTML/URL/@提及，标准化空白字符"""
        if not text:
            return ''
        text = cls.HTML_PATTERN.sub(' ', text)
        text = cls.URL_PATTERN.sub(' ', text)
        text = cls.REPLY_PATTERN.sub('', text)
        text = cls.MENTION_PATTERN.sub(' ', text)
        if keep_topic:
            # 保留话题文字本身，去掉 # 号
            text = cls.TOPIC_PATTERN.sub(r'\1', text)
        text = cls.WHITESPACE_PATTERN.sub(' ', text)
        return text.strip()

    @classmethod
    def content_hash(cls, text: str) -> str:
        """基于标准化文本生成去重哈希"""
        normalized = re.sub(r'\W+', '', text.lower())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """过滤过短、无实质内容的文本"""
        if not text or len(text) < cls.MIN_CONTENT_LENGTH:
            return False
        # 过滤纯表情/符号内容
        return bool(re.search(r'[a-zA-Z0-9一-龥]', text))

    @classmethod
    def clean_batch(cls, records: list) -> tuple:
        """
        批量清洗原始记录。
        返回 (有效记录列表, 统计信息)。
        记录需包含 content 字段，清洗后附加 content_hash。
        """
        seen = set()
        cleaned = []
        stats = {'raw': len(records), 'invalid': 0, 'duplicated': 0, 'valid': 0}

        for record in records:
            text = cls.clean_text(record.get('content', ''))
            if not cls.is_valid(text):
                stats['invalid'] += 1
                continue

            digest = cls.content_hash(text)
            if digest in seen:
                stats['duplicated'] += 1
                continue
            seen.add(digest)

            record['content'] = text
            record['content_hash'] = digest
            cleaned.append(record)

        stats['valid'] = len(cleaned)
        return cleaned, stats

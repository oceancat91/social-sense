"""数据采集脚本（示例）"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def main():
    """执行数据采集任务"""
    print('Social Sense 数据采集脚本')
    print('=' * 40)
    print('提示: 请先配置好数据源 API 后再运行')
    print()
    print('支持的平台:')
    print('  - 微博 (weibo)')
    print('  - 知乎 (zhihu)')
    print()
    print('用法: python crawl.py --platform weibo --keyword "人工智能"')
    # TODO: 实现命令行参数解析和实际采集逻辑


if __name__ == '__main__':
    main()

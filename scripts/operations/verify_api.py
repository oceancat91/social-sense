"""分析 API 端到端验证脚本（需先启动后端服务）"""
import requests

BASE = 'http://localhost:5000/api/v1'


def main():
    r = requests.post(f'{BASE}/auth/login',
                      json={'email': 'admin@social-sense.com', 'password': 'admin123'})
    r.raise_for_status()
    h = {'Authorization': 'Bearer ' + r.json()['data']['token']}

    cp = requests.get(f'{BASE}/analysis/platform-comparison', headers=h).json()['data']['items']
    print('== 平台对比 ==')
    for i in cp:
        print(f"  {i['platform_name']}: 总量{i['total']} 正{i['positive']} "
              f"中{i['neutral']} 负{i['negative']} 均分{i['avg_score']} "
              f"负面率{i['negative_ratio']} 互动{i['engagement']}")

    tr = requests.get(f'{BASE}/analysis/trend?days=14', headers=h).json()['data']
    print('== 趋势 ==')
    print('  日期范围:', tr['dates'][0], '->', tr['dates'][-1])
    for p in tr['platforms']:
        print(f"  {p['platform_name']}: {p['data']}")

    pg = requests.get(f'{BASE}/analysis/propagation?days=14', headers=h).json()['data']
    print('== 传播溯源 ==')
    for i in pg['items']:
        print(f"  {i['platform_name']}: 首发{i['first_seen'][:16]} "
              f"延迟+{i['delay_hours']}h 峰值{i['peak_date']} 总量{i['total']}")

    kw = requests.get(f'{BASE}/analysis/keywords?top_k=10', headers=h).json()['data']['keywords']
    print('== 关键词TOP10 ==')
    print(' ', [(k['word'], k['count']) for k in kw])

    hot = requests.get(f'{BASE}/analysis/hot-content?limit=5', headers=h).json()['data']['items']
    print('== 热门TOP5 ==')
    for i in hot:
        print(f"  [{i['platform']}] {i['content'][:36]} 赞{i['like_count']} 情感{i['sentiment']}")

    td = requests.get(f'{BASE}/analysis/trending', headers=h).json()['data']['topics']
    print('== 热点话题 ==')
    print(' ', [(t['topic'], t['mentions'], t['heat']) for t in td[:5]])


if __name__ == '__main__':
    main()

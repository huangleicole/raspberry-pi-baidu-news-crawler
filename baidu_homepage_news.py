#!/usr/bin/env python3
"""
树莓派百度首页新闻推送脚本
作者：黄磊
功能：每日定时推送百度首页新闻到邮箱
"""

import smtplib
import requests
import json
import time
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
import os
from typing import List, Dict
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/baidu_homepage_news.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BaiduHomepageNewsCollector:
    """百度首页新闻收集器"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'DNT': '1',
            'Connection': 'keep-alive',
        }
    
    def fetch_baidu_homepage_news(self) -> List[Dict]:
        """获取百度首页新闻（前10条）"""
        news_items = []
        
        try:
            logger.info("正在抓取百度首页(www.baidu.com)新闻...")
            
            # 获取百度首页
            url = "https://www.baidu.com/"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.encoding = 'utf-8'
            
            # 保存HTML用于调试
            with open("/tmp/baidu_homepage.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("✓ 已保存百度首页HTML到 /tmp/baidu_homepage.html")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 方法1：查找百度首页的热点新闻
            news_items = self._parse_hot_news(soup)
            
            # 方法2：如果热点新闻没找到，尝试查找所有新闻链接
            if len(news_items) < 5:
                logger.info("热点新闻获取较少，尝试备用方法...")
                backup_items = self._parse_all_news_links(soup)
                news_items.extend(backup_items)
            
            # 方法3：尝试解析百度热搜榜
            if len(news_items) < 5:
                logger.info("尝试解析热搜榜...")
                hotsearch_items = self._parse_hotsearch(soup)
                news_items.extend(hotsearch_items)
            
            # 去重并限制数量
            seen_titles = set()
            unique_news = []
            
            for news in news_items:
                if news['title'] and news['title'] not in seen_titles:
                    seen_titles.add(news['title'])
                    unique_news.append(news)
                if len(unique_news) >= 10:
                    break
            
            logger.info(f"成功收集到 {len(unique_news)} 条百度首页新闻")
            return unique_news[:10]
            
        except Exception as e:
            logger.error(f"获取百度首页新闻失败: {e}")
            # 返回示例数据作为备份
            return self._get_backup_news()
    
    def _parse_hot_news(self, soup) -> List[Dict]:
        """解析百度首页热点新闻"""
        news_list = []
        
        try:
            # 百度首页热点新闻通常在这些位置
            hot_selectors = [
                '#hotsearch-content-wrapper .hotsearch-item',  # 热点新闻项
                '.s-hotsearch-title',                          # 热搜标题
                '.hot-title',                                   # 热点标题
                '[class*="hot"] a',                            # 包含hot的类
                '[class*="news"] a',                           # 包含news的类
            ]
            
            for selector in hot_selectors:
                items = soup.select(selector)
                logger.info(f"热点选择器 '{selector}' 找到 {len(items)} 个元素")
                
                for item in items[:10]:
                    try:
                        title = self._clean_title(item.text)
                        if not title or len(title) < 3:
                            continue
                        
                        link = self._fix_link(item.get('href', ''))
                        
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': '百度热点新闻',
                            'source': '百度首页',
                            'type': '热点'
                        })
                        
                    except Exception as e:
                        logger.debug(f"解析热点新闻失败: {e}")
                        continue
                
                if news_list:
                    break
            
            return news_list
            
        except Exception as e:
            logger.error(f"解析热点新闻失败: {e}")
            return []
    
    def _parse_hotsearch(self, soup) -> List[Dict]:
        """解析百度热搜榜"""
        news_list = []
        
        try:
            # 查找热搜榜相关元素
            hotsearch_selectors = [
                '.hotsearch-item',
                '.s-news-rank-content .title-content',
                '[class*="rank"]',
                '[class*="hotsearch"]',
            ]
            
            for selector in hotsearch_selectors:
                items = soup.select(selector)
                logger.info(f"热搜选择器 '{selector}' 找到 {len(items)} 个元素")
                
                for item in items[:15]:
                    try:
                        title = self._clean_title(item.text)
                        if not title or len(title) < 3:
                            continue
                        
                        # 查找链接
                        link_tag = item.find('a')
                        link = self._fix_link(link_tag.get('href', '')) if link_tag else ""
                        
                        if not link:
                            link = f"https://www.baidu.com/s?wd={requests.utils.quote(title)}"
                        
                        news_list.append({
                            'title': title,
                            'link': link,
                            'summary': '百度热搜',
                            'source': '百度热搜榜',
                            'type': '热搜'
                        })
                        
                    except Exception as e:
                        logger.debug(f"解析热搜项失败: {e}")
                        continue
                
                if len(news_list) >= 5:
                    break
            
            return news_list
            
        except Exception as e:
            logger.error(f"解析热搜榜失败: {e}")
            return []
    
    def _parse_all_news_links(self, soup) -> List[Dict]:
        """解析所有可能的新闻链接"""
        news_list = []
        
        try:
            # 查找所有链接
            all_links = soup.find_all('a', href=True)
            logger.info(f"找到 {len(all_links)} 个链接")
            
            news_keywords = [
                '新闻', '报道', '消息', '资讯', '热点', '最新', '今日',
                '疫情', '政策', '经济', '科技', '体育', '娱乐', '财经'
            ]
            
            for link in all_links:
                try:
                    title = self._clean_title(link.text)
                    if not title or len(title) < 5 or len(title) > 100:
                        continue
                    
                    # 检查是否包含新闻关键词
                    has_news_keyword = any(keyword in title for keyword in news_keywords)
                    if not has_news_keyword:
                        continue
                    
                    href = link.get('href', '')
                    if not href or href == '#' or href.startswith('javascript'):
                        continue
                    
                    link_url = self._fix_link(href)
                    
                    news_list.append({
                        'title': title,
                        'link': link_url,
                        'summary': '百度首页资讯',
                        'source': '百度',
                        'type': '资讯'
                    })
                    
                    if len(news_list) >= 15:
                        break
                        
                except Exception as e:
                    continue
            
            return news_list
            
        except Exception as e:
            logger.error(f"解析所有链接失败: {e}")
            return []
    
    def _clean_title(self, title: str) -> str:
        """清理标题"""
        if not title:
            return ""
        
        # 移除多余空白字符
        title = re.sub(r'\s+', ' ', title.strip())
        
        # 过滤太短或无效的标题
        if len(title) < 3:
            return ""
        
        return title
    
    def _fix_link(self, link: str) -> str:
        """修复链接"""
        if not link:
            return "https://www.baidu.com"
        
        # 如果是相对路径，转换为绝对路径
        if link.startswith('//'):
            return 'https:' + link
        elif link.startswith('/'):
            return 'https://www.baidu.com' + link
        elif not link.startswith('http'):
            return 'https://' + link
        
        return link
    
    def _get_backup_news(self) -> List[Dict]:
        """获取备用新闻数据"""
        current_time = datetime.now().strftime('%H:%M')
        return [{
            'title': '百度首页热点新闻',
            'link': 'https://www.baidu.com',
            'summary': f'当前时间 {current_time} 的首页新闻',
            'source': '百度首页',
            'type': '示例'
        }]

class EmailSender:
    """邮件发送器"""
    
    def __init__(self, config_path: str = 'email_config.json'):
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: str) -> Dict:
        """加载邮件配置"""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info("✓ 从配置文件加载邮件配置")
                    return config
            except Exception as e:
                logger.error(f"读取配置文件失败: {e}")
        
        # 默认配置
        default_config = {
            "smtp_server": "smtp.qq.com",
            "smtp_port": 465,
            "sender_email": "",
            "sender_password": "",
            "receiver_email": "",
            "use_ssl": True,
            "use_tls": False
        }
        
        logger.warning("⚠ 使用默认配置，请修改email_config.json")
        return default_config
    
    def create_email_content(self, news_items: List[Dict]) -> str:
        """创建邮件内容 - 百度首页新闻版"""
        current_time = datetime.now().strftime('%Y年%m月%d日 %H:%M')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f5f7fa; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; background-color: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #2932e1 0%, #1a237e 100%); color: white; padding: 25px; border-radius: 8px; margin-bottom: 25px; text-align: center; }}
                .header h1 {{ margin: 0 0 10px 0; font-size: 28px; }}
                .header p {{ margin: 5px 0; opacity: 0.9; }}
                .news-item {{ border-left: 5px solid #2932e1; padding: 18px; margin-bottom: 18px; background-color: #f8f9fa; border-radius: 0 8px 8px 0; transition: all 0.3s; }}
                .news-item:hover {{ transform: translateX(5px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
                .news-rank {{ display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; background-color: #2932e1; color: white; border-radius: 50%; font-weight: bold; margin-right: 12px; }}
                .news-title {{ display: inline-block; font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #2c3e50; }}
                .news-meta {{ color: #666; font-size: 14px; margin-bottom: 8px; }}
                .news-type {{ display: inline-block; background-color: #ff6b6b; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }}
                .news-summary {{ color: #444; line-height: 1.7; margin-bottom: 12px; }}
                .news-link {{ color: #2932e1; text-decoration: none; font-weight: bold; display: inline-block; margin-top: 8px; }}
                .news-link:hover {{ text-decoration: underline; }}
                .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #7f8c8d; font-size: 13px; text-align: center; }}
                .baidu-logo {{ color: #2932e1; font-weight: bold; }}
                .time-badge {{ background-color: #e3f2fd; color: #1565c0; padding: 4px 12px; border-radius: 15px; font-size: 14px; display: inline-block; margin-left: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔍 百度首页新闻推送</h1>
                    <p>📅 推送时间：{current_time} <span class="time-badge">实时更新</span></p>
                    <p>📊 今日新闻数量：{len(news_items)}条</p>
                </div>
        """
        
        for i, news in enumerate(news_items, 1):
            type_display = f'<span class="news-type">{news.get("type", "新闻")}</span>'
            
            html_content += f"""
                <div class="news-item">
                    <span class="news-rank">{i}</span>
                    <div class="news-title">{news.get('title', '')} {type_display}</div>
                    <div class="news-meta">
                        📍 来源：<span class="baidu-logo">{news.get('source', '百度首页')}</span>
                    </div>
                    <div class="news-summary">{news.get('summary', '')}</div>
                    <a href="{news.get('link', '#')}" class="news-link" target="_blank">📖 查看详情 →</a>
                </div>
            """
        
        html_content += f"""
                <div class="footer">
                    <p>本邮件由黄磊的树莓派自动发送 | 数据来源：百度首页(www.baidu.com)</p>
                    <p>发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 技术支持：树莓派4B</p>
                    <p>💡 百度首页实时更新，反映当前最受关注的新闻事件</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def send_email_with_retry(self, subject: str, html_content: str, max_retries: int = 3) -> bool:
        """发送邮件，带重试机制"""
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试发送邮件 (第{attempt+1}次尝试)")
                
                # 检查配置
                if not all([self.config.get('sender_email'), 
                          self.config.get('sender_password'), 
                          self.config.get('receiver_email')]):
                    logger.error("❌ 邮箱配置不完整，请检查email_config.json")
                    return False
                
                # 创建邮件
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = self.config['sender_email']
                msg['To'] = self.config['receiver_email']
                
                # 添加HTML内容
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)
                
                # 根据配置选择连接方式
                smtp_server = self.config['smtp_server']
                smtp_port = int(self.config.get('smtp_port', 465))
                use_ssl = self.config.get('use_ssl', False)
                use_tls = self.config.get('use_tls', False)
                
                logger.info(f"连接到 {smtp_server}:{smtp_port} (SSL:{use_ssl}, TLS:{use_tls})")
                
                # 连接服务器
                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
                else:
                    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                    server.ehlo()
                    if use_tls:
                        server.starttls()
                        server.ehlo()
                
                # 登录
                server.login(self.config['sender_email'], self.config['sender_password'])
                
                # 发送邮件
                server.send_message(msg)
                server.quit()
                
                logger.info(f"✅ 邮件发送成功 (第{attempt+1}次尝试)")
                return True
                
            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"❌ 邮箱认证失败: {e}")
                logger.error("请检查：1.邮箱是否正确 2.是否使用授权码(非密码) 3.是否开启SMTP服务")
                return False
                
            except Exception as e:
                logger.error(f"❌ 发送失败 (尝试{attempt+1}/{max_retries}): {type(e).__name__}: {str(e)[:100]}")
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3
                    logger.info(f"等待{wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue
        
        logger.error(f"❌ 邮件发送失败，已重试{max_retries}次")
        return False

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🔍 百度首页新闻推送任务开始执行")
    
    try:
        # 检查网络连接
        logger.info("检查网络连接...")
        try:
            response = requests.get("https://www.baidu.com", timeout=5)
            logger.info(f"✓ 网络连接正常 (状态码: {response.status_code})")
        except Exception as e:
            logger.warning(f"⚠ 网络连接可能有问题: {e}")
        
        # 收集新闻
        news_collector = BaiduHomepageNewsCollector()
        news_items = news_collector.fetch_baidu_homepage_news()
        
        if not news_items:
            logger.error("❌ 未能获取到新闻")
            return False
        
        logger.info(f"✅ 成功收集到 {len(news_items)} 条百度首页新闻")
        
        # 显示新闻标题（用于调试）
        for i, news in enumerate(news_items, 1):
            logger.info(f"{i:2d}. {news['title']}")
        
        # 创建邮件内容
        email_sender = EmailSender()
        current_date = datetime.now().strftime('%Y年%m月%d日')
        subject = f"🔍 百度首页新闻TOP{len(news_items)} {current_date}"
        
        html_content = email_sender.create_email_content(news_items)
        
        # 发送邮件
        success = email_sender.send_email_with_retry(subject, html_content)
        
        if success:
            logger.info("✅ 百度首页新闻推送任务完成")
            save_backup(news_items)
        else:
            logger.error("❌ 邮件发送失败，但新闻已收集")
            save_backup(news_items)
            logger.info("📁 新闻已保存到本地备份文件")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ 任务执行失败: {e}", exc_info=True)
        return False

def save_backup(news_items: List[Dict]):
    """保存新闻到本地备份文件"""
    try:
        backup_dir = "/home/send_news/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        filename = f"baidu_homepage_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(backup_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"百度首页新闻备份 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n")
            for i, news in enumerate(news_items, 1):
                f.write(f"{i}. {news.get('title', '')}\n")
                f.write(f"   链接: {news.get('link', '')}\n")
                f.write(f"   来源: {news.get('source', '')}\n")
                f.write("-" * 30 + "\n")
        
        logger.info(f"📄 新闻备份已保存: {filepath}")
    except Exception as e:
        logger.error(f"保存备份失败: {e}")

if __name__ == "__main__":
    start_time = time.time()
    
    success = main()
    
    elapsed_time = time.time() - start_time
    logger.info(f"⏱️ 任务执行耗时: {elapsed_time:.2f}秒")
    logger.info("=" * 60)
    
    exit(0 if success else 1)
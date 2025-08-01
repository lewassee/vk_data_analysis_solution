#!/usr/bin/env python3
"""
VK Data Analyzer - Система анализа данных из группы ВКонтакте
Анализирует собранные посты и комментарии для выявления трендов, популярных тем и мнений
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import re
from typing import Dict, List, Any, Tuple
import os
from wordcloud import WordCloud
import matplotlib.font_manager as fm

# Настройка шрифтов для корректного отображения русского текста
plt.rcParams['font.family'] = ['DejaVu Sans', 'Liberation Sans', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

class VKDataAnalyzer:
    def __init__(self, data_file: str):
        """
        Инициализация анализатора данных
        
        Args:
            data_file: Путь к JSON файлу с данными
        """
        self.data_file = data_file
        self.data = self._load_data()
        self.posts_df = self._prepare_posts_dataframe()
        self.comments_df = self._prepare_comments_dataframe()
        
    def _load_data(self) -> Dict[str, Any]:
        """Загрузка данных из JSON файла"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки данных: {e}")
            return {}
    
    def _prepare_posts_dataframe(self) -> pd.DataFrame:
        """Подготовка DataFrame для постов"""
        posts = self.data.get('posts', [])
        
        posts_data = []
        for post in posts:
            posts_data.append({
                'id': post.get('id'),
                'date': datetime.fromtimestamp(post.get('date', 0)),
                'text': post.get('text', ''),
                'likes_count': post.get('likes', {}).get('count', 0),
                'reposts_count': post.get('reposts', {}).get('count', 0),
                'comments_count': post.get('comments', {}).get('count', 0),
                'views_count': post.get('views', {}).get('count', 0),
                'from_id': post.get('from_id'),
                'text_length': len(post.get('text', ''))
            })
        
        df = pd.DataFrame(posts_data)
        if not df.empty:
            df['engagement'] = df['likes_count'] + df['reposts_count'] + df['comments_count']
            df['engagement_rate'] = df['engagement'] / (df['views_count'] + 1)  # +1 чтобы избежать деления на 0
        
        return df
    
    def _prepare_comments_dataframe(self) -> pd.DataFrame:
        """Подготовка DataFrame для комментариев"""
        comments = self.data.get('comments', [])
        
        comments_data = []
        for comment in comments:
            comments_data.append({
                'id': comment.get('id'),
                'parent_post_id': comment.get('parent_post_id'),
                'date': datetime.fromtimestamp(comment.get('date', 0)),
                'text': comment.get('text', ''),
                'likes_count': comment.get('likes', {}).get('count', 0),
                'from_id': comment.get('from_id'),
                'text_length': len(comment.get('text', ''))
            })
        
        return pd.DataFrame(comments_data)
    
    def get_basic_statistics(self) -> Dict[str, Any]:
        """Получение базовой статистики"""
        stats = {
            'total_posts': len(self.posts_df),
            'total_comments': len(self.comments_df),
            'date_range': {
                'start': self.posts_df['date'].min().isoformat() if not self.posts_df.empty else None,
                'end': self.posts_df['date'].max().isoformat() if not self.posts_df.empty else None
            },
            'engagement_stats': {
                'avg_likes_per_post': self.posts_df['likes_count'].mean() if not self.posts_df.empty else 0,
                'avg_comments_per_post': self.posts_df['comments_count'].mean() if not self.posts_df.empty else 0,
                'avg_reposts_per_post': self.posts_df['reposts_count'].mean() if not self.posts_df.empty else 0,
                'total_engagement': self.posts_df['engagement'].sum() if not self.posts_df.empty else 0
            }
        }
        
        return stats
    
    def analyze_posting_patterns(self) -> Dict[str, Any]:
        """Анализ паттернов публикации постов"""
        if self.posts_df.empty:
            return {}
        
        # Анализ по дням недели
        self.posts_df['weekday'] = self.posts_df['date'].dt.day_name()
        weekday_counts = self.posts_df['weekday'].value_counts()
        
        # Анализ по часам
        self.posts_df['hour'] = self.posts_df['date'].dt.hour
        hour_counts = self.posts_df['hour'].value_counts().sort_index()
        
        # Анализ по месяцам
        self.posts_df['month'] = self.posts_df['date'].dt.to_period('M')
        month_counts = self.posts_df['month'].value_counts().sort_index()
        
        return {
            'posts_by_weekday': weekday_counts.to_dict(),
            'posts_by_hour': hour_counts.to_dict(),
            'posts_by_month': {str(k): v for k, v in month_counts.to_dict().items()}
        }
    
    def extract_keywords(self, text_series: pd.Series, min_length: int = 3, top_n: int = 50) -> List[Tuple[str, int]]:
        """Извлечение ключевых слов из текста"""
        # Объединяем весь текст
        all_text = ' '.join(text_series.fillna('').astype(str))
        
        # Очистка текста и извлечение слов
        # Удаляем URL, упоминания, хештеги
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', all_text)
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'#\w+', '', text)
        
        # Извлекаем слова (только кириллица и латиница)
        words = re.findall(r'[а-яёА-ЯЁa-zA-Z]+', text.lower())
        
        # Фильтруем по длине и исключаем стоп-слова
        stop_words = {
            'это', 'что', 'как', 'для', 'или', 'при', 'все', 'так', 'уже', 'еще', 'где', 'кто',
            'его', 'она', 'они', 'мне', 'нас', 'вас', 'них', 'тут', 'там', 'тоже', 'если',
            'чтобы', 'когда', 'после', 'перед', 'между', 'через', 'под', 'над', 'без', 'про',
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was',
            'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now',
            'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she',
            'too', 'use'
        }
        
        filtered_words = [word for word in words if len(word) >= min_length and word not in stop_words]
        
        # Подсчитываем частоту
        word_counts = Counter(filtered_words)
        
        return word_counts.most_common(top_n)
    
    def analyze_popular_topics(self) -> Dict[str, Any]:
        """Анализ популярных тем"""
        # Ключевые слова в постах
        post_keywords = self.extract_keywords(self.posts_df['text']) if not self.posts_df.empty else []
        
        # Ключевые слова в комментариях
        comment_keywords = self.extract_keywords(self.comments_df['text']) if not self.comments_df.empty else []
        
        # Анализ технических терминов АСУ ТП
        tech_terms = [
            'scada', 'plc', 'асу', 'тп', 'кипиа', 'контроллер', 'датчик', 'привод', 'модуль',
            'siemens', 'schneider', 'abb', 'omron', 'mitsubishi', 'allen', 'bradley',
            'wincc', 'tia', 'portal', 'step', 'codesys', 'unity', 'vijeo', 'citect',
            'modbus', 'profibus', 'profinet', 'ethernet', 'rs485', 'can', 'hart',
            'hmi', 'панель', 'оператор', 'визуализация', 'мнемосхема', 'тренд',
            'аварийный', 'сигнализация', 'блокировка', 'защита', 'автоматика'
        ]
        
        # Подсчет упоминаний технических терминов
        all_text = ' '.join(self.posts_df['text'].fillna('').astype(str)) + ' ' + \
                  ' '.join(self.comments_df['text'].fillna('').astype(str))
        all_text = all_text.lower()
        
        tech_mentions = {}
        for term in tech_terms:
            count = len(re.findall(r'\b' + re.escape(term) + r'\b', all_text))
            if count > 0:
                tech_mentions[term] = count
        
        return {
            'post_keywords': post_keywords[:20],
            'comment_keywords': comment_keywords[:20],
            'tech_terms_mentions': dict(sorted(tech_mentions.items(), key=lambda x: x[1], reverse=True)[:20])
        }
    
    def analyze_engagement_patterns(self) -> Dict[str, Any]:
        """Анализ паттернов вовлеченности"""
        if self.posts_df.empty:
            return {}
        
        # Топ постов по вовлеченности
        top_posts = self.posts_df.nlargest(10, 'engagement')[['id', 'text', 'engagement', 'likes_count', 'comments_count', 'reposts_count']]
        
        # Корреляция между различными метриками
        correlations = self.posts_df[['likes_count', 'comments_count', 'reposts_count', 'views_count', 'text_length']].corr()
        
        # Анализ длины текста и вовлеченности
        text_length_bins = pd.cut(self.posts_df['text_length'], bins=5, labels=['Очень короткие', 'Короткие', 'Средние', 'Длинные', 'Очень длинные'])
        engagement_by_length = self.posts_df.groupby(text_length_bins)['engagement'].mean()
        
        return {
            'top_posts': top_posts.to_dict('records'),
            'correlations': correlations.to_dict(),
            'engagement_by_text_length': engagement_by_length.to_dict()
        }
    
    def create_visualizations(self, output_dir: str = 'analysis_results'):
        """Создание визуализаций"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. Активность по дням недели
        if not self.posts_df.empty:
            plt.figure(figsize=(12, 6))
            weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            weekday_counts = self.posts_df['weekday'].value_counts().reindex(weekday_order, fill_value=0)
            
            plt.subplot(1, 2, 1)
            weekday_counts.plot(kind='bar')
            plt.title('Активность публикаций по дням недели')
            plt.xlabel('День недели')
            plt.ylabel('Количество постов')
            plt.xticks(rotation=45)
            
            # 2. Активность по часам
            plt.subplot(1, 2, 2)
            hour_counts = self.posts_df['hour'].value_counts().sort_index()
            hour_counts.plot(kind='line', marker='o')
            plt.title('Активность публикаций по часам')
            plt.xlabel('Час')
            plt.ylabel('Количество постов')
            plt.grid(True)
            
            plt.tight_layout()
            plt.savefig(f'{output_dir}/posting_patterns.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 3. Распределение вовлеченности
        if not self.posts_df.empty:
            plt.figure(figsize=(15, 10))
            
            plt.subplot(2, 2, 1)
            plt.hist(self.posts_df['likes_count'], bins=30, alpha=0.7, color='blue')
            plt.title('Распределение лайков')
            plt.xlabel('Количество лайков')
            plt.ylabel('Частота')
            
            plt.subplot(2, 2, 2)
            plt.hist(self.posts_df['comments_count'], bins=30, alpha=0.7, color='green')
            plt.title('Распределение комментариев')
            plt.xlabel('Количество комментариев')
            plt.ylabel('Частота')
            
            plt.subplot(2, 2, 3)
            plt.hist(self.posts_df['reposts_count'], bins=30, alpha=0.7, color='red')
            plt.title('Распределение репостов')
            plt.xlabel('Количество репостов')
            plt.ylabel('Частота')
            
            plt.subplot(2, 2, 4)
            plt.scatter(self.posts_df['text_length'], self.posts_df['engagement'], alpha=0.6)
            plt.title('Длина текста vs Вовлеченность')
            plt.xlabel('Длина текста (символы)')
            plt.ylabel('Общая вовлеченность')
            
            plt.tight_layout()
            plt.savefig(f'{output_dir}/engagement_analysis.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 4. Топ ключевых слов
        topics = self.analyze_popular_topics()
        if topics.get('post_keywords'):
            plt.figure(figsize=(12, 8))
            
            keywords = topics['post_keywords'][:15]
            words, counts = zip(*keywords)
            
            plt.barh(range(len(words)), counts)
            plt.yticks(range(len(words)), words)
            plt.title('Топ-15 ключевых слов в постах')
            plt.xlabel('Частота упоминаний')
            plt.gca().invert_yaxis()
            
            plt.tight_layout()
            plt.savefig(f'{output_dir}/top_keywords.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 5. Технические термины
        if topics.get('tech_terms_mentions'):
            plt.figure(figsize=(12, 8))
            
            tech_terms = list(topics['tech_terms_mentions'].items())[:15]
            terms, counts = zip(*tech_terms)
            
            plt.barh(range(len(terms)), counts)
            plt.yticks(range(len(terms)), terms)
            plt.title('Топ-15 технических терминов АСУ ТП')
            plt.xlabel('Частота упоминаний')
            plt.gca().invert_yaxis()
            
            plt.tight_layout()
            plt.savefig(f'{output_dir}/tech_terms.png', dpi=300, bbox_inches='tight')
            plt.close()
    
    def generate_report(self, output_file: str = 'analysis_report.json'):
        """Генерация полного отчета анализа"""
        report = {
            'basic_statistics': self.get_basic_statistics(),
            'posting_patterns': self.analyze_posting_patterns(),
            'popular_topics': self.analyze_popular_topics(),
            'engagement_patterns': self.analyze_engagement_patterns(),
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"Отчет сохранен в {output_file}")
        return report


def main():
    """Основная функция для запуска анализа"""
    # Путь к файлу с данными
    data_file = 'vk_data/big_asu_data_20250801_062558.json'
    
    if not os.path.exists(data_file):
        print(f"Файл данных {data_file} не найден!")
        return
    
    # Создаем анализатор
    analyzer = VKDataAnalyzer(data_file)
    
    # Генерируем отчет
    report = analyzer.generate_report('analysis_results/analysis_report.json')
    
    # Создаем визуализации
    analyzer.create_visualizations('analysis_results')
    
    # Выводим краткую статистику
    stats = report['basic_statistics']
    print("\n=== КРАТКАЯ СТАТИСТИКА ===")
    print(f"Всего постов: {stats['total_posts']}")
    print(f"Всего комментариев: {stats['total_comments']}")
    print(f"Период данных: {stats['date_range']['start']} - {stats['date_range']['end']}")
    print(f"Среднее количество лайков на пост: {stats['engagement_stats']['avg_likes_per_post']:.1f}")
    print(f"Среднее количество комментариев на пост: {stats['engagement_stats']['avg_comments_per_post']:.1f}")
    
    # Топ ключевые слова
    topics = report['popular_topics']
    print("\n=== ТОП-10 КЛЮЧЕВЫХ СЛОВ ===")
    for word, count in topics['post_keywords'][:10]:
        print(f"{word}: {count}")
    
    # Топ технические термины
    print("\n=== ТОП-10 ТЕХНИЧЕСКИХ ТЕРМИНОВ ===")
    for term, count in list(topics['tech_terms_mentions'].items())[:10]:
        print(f"{term}: {count}")
    
    print(f"\nАнализ завершен! Результаты сохранены в папке 'analysis_results'")


if __name__ == "__main__":
    main()


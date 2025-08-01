#!/usr/bin/env python3
"""
VK Group Parser - Парсер для сбора данных из группы ВКонтакте
Собирает посты, комментарии и метаданные для дальнейшего анализа
"""

import requests
import json
import time
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Any
import os

class VKGroupParser:
    def __init__(self, access_token: str, api_version: str = "5.131"):
        """
        Инициализация парсера VK API
        
        Args:
            access_token: Токен доступа к VK API
            api_version: Версия API VK
        """
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = "https://api.vk.com/method/"
        self.session = requests.Session()
        
    def _make_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполнение запроса к VK API
        
        Args:
            method: Название метода API
            params: Параметры запроса
            
        Returns:
            Ответ API в формате JSON
        """
        params.update({
            'access_token': self.access_token,
            'v': self.api_version
        })
        
        url = f"{self.base_url}{method}"
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error' in data:
                print(f"VK API Error: {data['error']}")
                return {}
                
            return data.get('response', {})
            
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return {}
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return {}
    
    def get_group_info(self, group_id: str) -> Dict[str, Any]:
        """
        Получение информации о группе
        
        Args:
            group_id: ID группы (например, 'big_asu')
            
        Returns:
            Информация о группе
        """
        params = {
            'group_ids': group_id,
            'fields': 'members_count,description,status,activity,site,links'
        }
        
        response = self._make_request('groups.getById', params)
        
        if response and len(response) > 0:
            return response[0]
        return {}
    
    def get_wall_posts(self, group_id: str, count: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получение постов со стены группы
        
        Args:
            group_id: ID группы
            count: Количество постов для получения (максимум 100)
            offset: Смещение для пагинации
            
        Returns:
            Список постов
        """
        # Сначала получаем числовой ID группы по её короткому имени
        if not group_id.isdigit() and not group_id.startswith('-'):
            group_info = self.get_group_info(group_id)
            if group_info and 'id' in group_info:
                numeric_group_id = group_info['id']
            else:
                print(f"Не удалось получить ID группы для {group_id}")
                return []
        else:
            numeric_group_id = group_id.lstrip('-')
        
        params = {
            'owner_id': f'-{numeric_group_id}',
            'count': min(count, 100),
            'offset': offset,
            'extended': 1,
            'filter': 'all'
        }
        
        response = self._make_request('wall.get', params)
        
        if response and 'items' in response:
            return response['items']
        return []
    
    def get_post_comments(self, group_id: str, post_id: int, count: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Получение комментариев к посту
        
        Args:
            group_id: ID группы
            post_id: ID поста
            count: Количество комментариев для получения
            offset: Смещение для пагинации
            
        Returns:
            Список комментариев
        """
        # Получаем числовой ID группы
        if not group_id.isdigit() and not group_id.startswith('-'):
            group_info = self.get_group_info(group_id)
            if group_info and 'id' in group_info:
                numeric_group_id = group_info['id']
            else:
                print(f"Не удалось получить ID группы для {group_id}")
                return []
        else:
            numeric_group_id = group_id.lstrip('-')
        
        params = {
            'owner_id': f'-{numeric_group_id}',
            'post_id': post_id,
            'count': min(count, 100),
            'offset': offset,
            'extended': 1,
            'sort': 'asc'
        }
        
        response = self._make_request('wall.getComments', params)
        
        if response and 'items' in response:
            return response['items']
        return []
    
    def parse_group_data(self, group_id: str, max_posts: int = 1000, include_comments: bool = True, 
                        start_date: datetime = None, end_date: datetime = None) -> Dict[str, Any]:
        """
        Полный парсинг данных группы
        
        Args:
            group_id: ID группы
            max_posts: Максимальное количество постов для парсинга
            include_comments: Включать ли комментарии
            start_date: Начальная дата для фильтрации постов (включительно)
            end_date: Конечная дата для фильтрации постов (включительно)
            
        Returns:
            Словарь с собранными данными
        """
        print(f"Начинаю парсинг группы: {group_id}")
        
        # Преобразуем даты в timestamp для сравнения
        start_timestamp = int(start_date.timestamp()) if start_date else None
        end_timestamp = int(end_date.timestamp()) if end_date else None
        
        if start_date and end_date:
            print(f"Фильтрация по периоду: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
        elif start_date:
            print(f"Фильтрация с даты: {start_date.strftime('%Y-%m-%d')}")
        elif end_date:
            print(f"Фильтрация до даты: {end_date.strftime('%Y-%m-%d')}")
        
        # Получаем информацию о группе
        group_info = self.get_group_info(group_id)
        print(f"Информация о группе получена: {group_info.get('name', 'Unknown')}")
        
        # Собираем посты
        all_posts = []
        posts_collected = 0
        offset = 0
        posts_in_period = 0
        
        while posts_collected < max_posts:
            batch_size = min(100, max_posts - posts_collected)
            posts = self.get_wall_posts(group_id, count=batch_size, offset=offset)
            
            if not posts:
                break
            
            # Фильтруем посты по дате если указан период
            filtered_posts = []
            for post in posts:
                post_date = post.get('date', 0)
                
                # Проверяем, попадает ли пост в указанный период
                if start_timestamp and post_date < start_timestamp:
                    # Если пост старше начальной даты, прекращаем сбор
                    print(f"Достигнута начальная дата фильтра. Прекращаю сбор.")
                    break
                
                if end_timestamp and post_date > end_timestamp:
                    # Если пост новее конечной даты, пропускаем
                    continue
                
                if start_timestamp and post_date >= start_timestamp:
                    # Пост попадает в период
                    filtered_posts.append(post)
                    posts_in_period += 1
                elif not start_timestamp:
                    # Если начальная дата не указана, берем все посты до конечной даты
                    filtered_posts.append(post)
                    posts_in_period += 1
            
            # Если нет постов в текущей партии, которые попадают в период, прекращаем
            if not filtered_posts and start_timestamp:
                break
            
            all_posts.extend(filtered_posts)
            posts_collected += len(posts)
            offset += len(posts)
            
            print(f"Собрано постов: {posts_collected}, в периоде: {posts_in_period}")
            
            # Пауза между запросами для соблюдения лимитов API
            time.sleep(0.5)
        
        # Собираем комментарии если требуется
        all_comments = []
        if include_comments:
            print("Начинаю сбор комментариев...")
            
            for i, post in enumerate(all_posts):
                post_id = post.get('id')
                if post_id and post.get('comments', {}).get('count', 0) > 0:
                    comments = self.get_post_comments(group_id, post_id)
                    
                    # Добавляем post_id к каждому комментарию для связи
                    for comment in comments:
                        comment['parent_post_id'] = post_id
                    
                    all_comments.extend(comments)
                    
                    if (i + 1) % 10 == 0:
                        print(f"Обработано постов для комментариев: {i + 1}/{len(all_posts)}")
                    
                    # Пауза между запросами
                    time.sleep(0.3)
        
        return {
            'group_info': group_info,
            'posts': all_posts,
            'comments': all_comments,
            'collection_timestamp': datetime.now().isoformat(),
            'total_posts': len(all_posts),
            'total_comments': len(all_comments),
            'filter_period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'posts_in_period': posts_in_period
            }
        }
    
    def save_to_json(self, data: Dict[str, Any], filename: str):
        """
        Сохранение данных в JSON файл
        
        Args:
            data: Данные для сохранения
            filename: Имя файла
        """
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Данные сохранены в {filename}")
    
    def save_to_csv(self, data: Dict[str, Any], posts_filename: str, comments_filename: str = None):
        """
        Сохранение данных в CSV файлы
        
        Args:
            data: Данные для сохранения
            posts_filename: Имя файла для постов
            comments_filename: Имя файла для комментариев
        """
        # Сохраняем посты
        posts = data.get('posts', [])
        if posts:
            with open(posts_filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'id', 'date', 'text', 'likes_count', 'reposts_count', 
                    'comments_count', 'views_count', 'from_id'
                ])
                writer.writeheader()
                
                for post in posts:
                    writer.writerow({
                        'id': post.get('id'),
                        'date': datetime.fromtimestamp(post.get('date', 0)).isoformat(),
                        'text': post.get('text', ''),
                        'likes_count': post.get('likes', {}).get('count', 0),
                        'reposts_count': post.get('reposts', {}).get('count', 0),
                        'comments_count': post.get('comments', {}).get('count', 0),
                        'views_count': post.get('views', {}).get('count', 0),
                        'from_id': post.get('from_id')
                    })
            print(f"Посты сохранены в {posts_filename}")
        
        # Сохраняем комментарии
        if comments_filename:
            comments = data.get('comments', [])
            if comments:
                with open(comments_filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'id', 'parent_post_id', 'date', 'text', 'likes_count', 'from_id'
                    ])
                    writer.writeheader()
                    
                    for comment in comments:
                        writer.writerow({
                            'id': comment.get('id'),
                            'parent_post_id': comment.get('parent_post_id'),
                            'date': datetime.fromtimestamp(comment.get('date', 0)).isoformat(),
                            'text': comment.get('text', ''),
                            'likes_count': comment.get('likes', {}).get('count', 0),
                            'from_id': comment.get('from_id')
                        })
                print(f"Комментарии сохранены в {comments_filename}")


def main():
    """
    Основная функция для запуска парсера
    """
    # Токен доступа (замените на ваш)
    ACCESS_TOKEN = "vk1.a.uAiwVO4hq2_W52EJpBCfIFIdu3W3f6f73etNpaq665qxnl8KDlbY___BZfQa13TH7UvKj4a_rRancrrOaySjeOyPVP0f6hjIqHiojrzwGJGgdRjiYMpKlE2GVONo0Owtb3UmyETIiUN3qB-fA-MrsFS9ypQn7JqOsxQmWKyiBBPYLMSzvSRK63CjvHAScDCt2QJx0IJTOv8S4Q7AauWDtg"
    
    # ID группы (без знака минус)
    GROUP_ID = "big_asu"
    
    # Создаем парсер
    parser = VKGroupParser(ACCESS_TOKEN)
    
    # Пример: собираем данные за последний месяц
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Парсим данные группы с фильтром по дате
    data = parser.parse_group_data(
        group_id=GROUP_ID,
        max_posts=500,  # Ограничиваем для тестирования
        include_comments=True,
        start_date=start_date,
        end_date=end_date
    )
    
    # Создаем директорию для результатов
    os.makedirs('vk_data', exist_ok=True)
    
    # Сохраняем данные
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    parser.save_to_json(data, f'vk_data/big_asu_data_{timestamp}.json')
    parser.save_to_csv(
        data, 
        f'vk_data/big_asu_posts_{timestamp}.csv',
        f'vk_data/big_asu_comments_{timestamp}.csv'
    )
    
    print(f"\nПарсинг завершен!")
    print(f"Собрано постов: {data['total_posts']}")
    print(f"Собрано комментариев: {data['total_comments']}")
    if data['filter_period']['start_date']:
        print(f"Период: {data['filter_period']['start_date'][:10]} - {data['filter_period']['end_date'][:10]}")
        print(f"Постов в периоде: {data['filter_period']['posts_in_period']}")


if __name__ == "__main__":
    main()


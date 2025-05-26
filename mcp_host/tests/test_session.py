from mcp_host.sessions import get_session_manager
import asyncio

async def test_session():
    # 세션 매니저 시작
    manager = get_session_manager()
    await manager.start()
    
    # 테스트 세션
    session_id = 'test_session'
    
    # 메시지 추가
    manager.add_user_message(session_id, '내 이름은 김철수야')
    manager.add_assistant_message(session_id, '안녕하세요, 김철수님!')
    manager.add_user_message(session_id, '내 이름이 뭐야?')
    
    # 히스토리 확인
    history = manager.get_conversation_history(session_id)
    print('대화 히스토리:')
    for i, msg in enumerate(history):
        print(f'{i+1}. {msg["role"]}: {msg["content"]}')
    
    await manager.stop()

if __name__ == "__main__":
    asyncio.run(test_session()) 
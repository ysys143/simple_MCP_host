// marked.js 백업 로드
if (typeof marked === 'undefined') {
    console.log('Primary CDN failed, loading backup...');
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/marked@11.1.1/marked.min.js';
    document.head.appendChild(script);
}

// 전역 변수들
let eventSource = null;  // WebSocket 대신 SSE 사용
let connectionStatus, serverCount, toolCount, chatContainer, messageInput, sendButton;
let typingIndicator = null;
let isSending = false;
let isComposing = false;
let sessionId = null;
let currentPartialMessage = null; // 스트리밍 메시지 추적
let currentToolCallsContainer = null; // 도구 호출 컨테이너 추적

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    // 요소 참조 저장
    connectionStatus = document.getElementById('connectionStatus');
    serverCount = document.getElementById('serverCount');
    toolCount = document.getElementById('toolCount');
    chatContainer = document.getElementById('chatContainer');
    messageInput = document.getElementById('messageInput');
    sendButton = document.getElementById('sendButton');
    
    // 키보드 이벤트 리스너 등록
    setupEventListeners();
    
    // 초기 연결
    connect();
});

// 이벤트 리스너 설정
function setupEventListeners() {
    console.log('이벤트 리스너 설정 시작');
    console.log('messageInput 요소:', messageInput);
    console.log('sendButton 요소:', sendButton);
    
    if (!messageInput) {
        console.error('messageInput 요소를 찾을 수 없습니다!');
        return;
    }
    
    if (!sendButton) {
        console.error('sendButton 요소를 찾을 수 없습니다!');
        return;
    }
    
    // Enter 키 처리
    messageInput.addEventListener('keydown', function(e) {
        console.log('키 이벤트 감지:', e.key, 'shiftKey:', e.shiftKey);
        
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            
            console.log('Enter 키 감지, isSending:', isSending, 'isComposing:', isComposing);
            
            // 전송 중이거나 IME 조합 중이면 무시
            if (isSending || isComposing) {
                console.log('전송 중이거나 IME 조합 중이므로 Enter 무시');
                return;
            }
            
            console.log('Enter 키로 sendMessage 호출');
            sendMessage();
        }
    });

    // 키보드 이벤트 추가 디버깅
    messageInput.addEventListener('keypress', function(e) {
        console.log('keypress 이벤트:', e.key, e.code);
    });

    messageInput.addEventListener('keyup', function(e) {
        console.log('keyup 이벤트:', e.key, e.code);
    });

    // IME 조합 이벤트
    messageInput.addEventListener('compositionstart', function(e) {
        isComposing = true;
        console.log('IME 조합 시작');
    });

    messageInput.addEventListener('compositionend', function(e) {
        isComposing = false;
        console.log('IME 조합 종료, 입력값:', e.target.value);
    });

    // 입력창 자동 크기 조절
    messageInput.addEventListener('input', autoResize);

    // 전송 버튼 클릭 이벤트
    sendButton.addEventListener('click', function(e) {
        e.preventDefault();
        console.log('전송 버튼 클릭');
        sendMessage();
    });

    // 명령어 예제 클릭 이벤트
    const commandExamples = document.querySelectorAll('.command-example');
    console.log('명령어 예제 개수:', commandExamples.length);
    commandExamples.forEach(example => {
        example.addEventListener('click', function() {
            const command = this.textContent.trim().substring(2); // 이모지 제거
            console.log('명령어 예제 클릭:', command);
            insertCommand(command);
        });
    });
    
    console.log('이벤트 리스너 설정 완료');
}

// 세션 ID 생성
function generateSessionId() {
    return 'web_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

function connect() {
    console.log('SSE 연결 시도 중...');
    updateConnectionStatus('initializing', '🟡 연결 중...');
    
    try {
        // 기존 SSE 연결이 있다면 종료
        if (eventSource) {
            eventSource.close();
        }

        // 세션 ID가 없을 때만 새로 생성 (재사용)
        if (!sessionId) {
            sessionId = generateSessionId();
            console.log('새 세션 ID 생성:', sessionId);
        } else {
            console.log('기존 세션 ID 재사용:', sessionId);
        }

        const url = `/api/v3/chat/stream?session_id=${sessionId}`;
        console.log('SSE 연결 URL:', url);
        
        eventSource = new EventSource(url);

        eventSource.onopen = function(event) {
            console.log('SSE 연결 열림');
            updateConnectionStatus('connected', '🟢 연결됨');
            loadSystemInfo();
        };

        eventSource.onmessage = function(event) {
            console.log('SSE 메시지 수신:', event.data);
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'partial_response') {
                    // 토큰 단위 스트리밍 처리
                    handlePartialResponse(data);
                } else if (data.type === 'final_response') {
                    // 최종 응답 처리
                    handleFinalResponse(data);
                    
                    // 응답 완료 시 전송 상태 재설정
                    resetSendingState();
                } else if (data.type === 'tool_call') {
                    // 도구 호출 시작 처리
                    handleToolCall(data);
                } else if (data.type === 'thinking' || data.type === 'acting' || data.type === 'observing') {
                    // 진행 상태 메시지는 무시하거나 로그만
                    console.log('진행 상태:', data.type, data.content);
                    
                    // observing 메시지 중 도구 결과인 경우 처리
                    if (data.type === 'observing' && data.metadata && data.metadata.observation_data && data.metadata.observation_data.tool) {
                        handleToolResult(data);
                    }
                } else if (data.type === 'error') {
                    // 오류 처리
                    hideTypingIndicator();
                    addAssistantMessage({ response: `오류가 발생했습니다: ${data.content}` });
                    
                    resetSendingState();
                } else {
                    console.log('기타 메시지 타입:', data.type);
                }
            } catch (e) {
                console.error('JSON 파싱 오류:', e.message);
                console.log('원본 데이터:', event.data);
            }
        };

        eventSource.onerror = function(event) {
            console.error('SSE 오류:', event);
            updateConnectionStatus('disconnected', '🔴 연결 끊김');
            setTimeout(connect, 3000); // 재연결 시도
        };
        
    } catch (error) {
        console.error('연결 시도 중 오류:', error);
        updateConnectionStatus('disconnected', '🔴 연결 오류');
    }
}

function handlePartialResponse(data) {
    if (!currentPartialMessage) {
        // 새로운 스트리밍 메시지 시작
        hideTypingIndicator(); // 타이핑 인디케이터 숨김
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant streaming';
        messageDiv.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <div class="streaming-content"></div>
                <div class="message-time">${new Date().toLocaleTimeString()}</div>
            </div>
        `;
        
        chatContainer.appendChild(messageDiv);
        currentPartialMessage = messageDiv;
        
        // 도구 호출 컨테이너 초기화 (새로운 응답 시작)
        currentToolCallsContainer = null;
        
        scrollToBottom();
    }
    
    // 스트리밍 내용 업데이트
    const contentDiv = currentPartialMessage.querySelector('.streaming-content');
    if (contentDiv) {
        contentDiv.innerHTML = renderMarkdown(data.content || '');
        scrollToBottom();
    }
}

function handleFinalResponse(data) {
    if (currentPartialMessage) {
        // 기존 스트리밍 메시지를 최종 응답으로 변경
        currentPartialMessage.className = 'message assistant';
        const contentDiv = currentPartialMessage.querySelector('.streaming-content');
        if (contentDiv) {
            contentDiv.innerHTML = renderMarkdown(data.content || '');
        }
        currentPartialMessage = null;
    } else {
        // 새로운 최종 응답 메시지 (스트리밍 없이)
        hideTypingIndicator();
        addAssistantMessage({ response: data.content });
    }
    scrollToBottom();
}

function handleToolCall(data) {
    // 도구 호출 박스 생성 또는 업데이트
    if (!currentToolCallsContainer) {
        // 타이핑 인디케이터 숨기기
        hideTypingIndicator();
        
        // 새로운 도구 호출 컨테이너 생성
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <div class="tool-calls-container"></div>
                <div class="message-time">${new Date().toLocaleTimeString()}</div>
            </div>
        `;
        
        chatContainer.appendChild(messageDiv);
        currentToolCallsContainer = messageDiv.querySelector('.tool-calls-container');
        scrollToBottom();
    }
    
    // 도구 호출 박스 추가
    const toolCallDiv = document.createElement('div');
    toolCallDiv.className = 'tool-call executing';
    toolCallDiv.setAttribute('data-server', data.metadata?.server || 'unknown');
    toolCallDiv.setAttribute('data-tool', data.metadata?.tool || 'unknown');
    
    toolCallDiv.innerHTML = `
        🔧 ${data.metadata?.server || 'unknown'}.${data.metadata?.tool || 'unknown'}() 
        <span class="tool-status">⏳ 실행 중...</span>
    `;
    
    currentToolCallsContainer.appendChild(toolCallDiv);
    scrollToBottom();
}

function handleToolResult(data) {
    // 해당 도구 호출 박스 업데이트
    if (currentToolCallsContainer) {
        const toolName = data.metadata.observation_data.tool;
        const success = data.metadata.observation_data.success;
        const result = data.content;
        
        // 해당 도구의 박스 찾기
        const toolBoxes = currentToolCallsContainer.querySelectorAll('.tool-call');
        const targetBox = Array.from(toolBoxes).find(box => 
            box.getAttribute('data-tool') === toolName && box.classList.contains('executing')
        );
        
        if (targetBox) {
            targetBox.classList.remove('executing');
            targetBox.classList.add(success ? 'success' : 'failed');
            
            const statusSpan = targetBox.querySelector('.tool-status');
            if (statusSpan) {
                statusSpan.innerHTML = success ? 'Succeed' : 'Failed';
            }
            
            // 결과 내용 추가
            const resultDiv = document.createElement('div');
            resultDiv.className = 'tool-result';
            resultDiv.textContent = result;
            targetBox.appendChild(resultDiv);
        }
        
        scrollToBottom();
    }
}

function updateConnectionStatus(status, text) {
    connectionStatus.className = `status ${status}`;
    const statusText = connectionStatus.querySelector('span');
    if (statusText) {
        statusText.textContent = text;
    } else {
        // span이 없으면 직접 텍스트 설정
        connectionStatus.innerHTML = `<span class="status-dot"></span><span>${text}</span>`;
    }
}

async function loadSystemInfo() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        if (data.status === 'healthy') {
            serverCount.textContent = `서버: ${data.connected_servers.length}개`;
            toolCount.textContent = `도구: ${data.available_tools_count}개`;
        }
    } catch (error) {
        console.error('시스템 정보 로드 오류:', error);
    }
}

function addUserMessage(content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    messageDiv.innerHTML = `
        <div class="message-avatar">👤</div>
        <div class="message-content">
            ${escapeHtml(content)}
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    try {
        console.log('마크다운 입력:', text);
        // marked.js를 사용하여 마크다운을 HTML로 변환
        const rendered = marked.parse(text);
        console.log('마크다운 출력:', rendered);
        return rendered;
    } catch (error) {
        console.error('마크다운 렌더링 오류:', error);
        // 실패시 기본 텍스트로 대체 (줄바꿈만 처리)
        return text.replace(/\n/g, '<br>');
    }
}

function addAssistantMessage(data) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    let content = data.response || '';
    let toolCallsHtml = '';
    
    // 도구 호출 정보는 별도 HTML로 생성
    if (data.tool_calls && data.tool_calls.length > 0) {
        toolCallsHtml = data.tool_calls.map(tool => `
            <div class="tool-call">
                🔧 ${tool.server}.${tool.tool}(${JSON.stringify(tool.arguments)})
                ${tool.success ? '✅' : '❌'} ${tool.execution_time_ms}ms
            </div>
        `).join('');
    }
    
    // 메시지 구성: 도구 호출 HTML + 응답 마크다운
    messageDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            ${toolCallsHtml}
            ${renderMarkdown(content)}
            <div class="message-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;
    
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function showTypingIndicator() {
    // 이미 표시 중이면 무시
    if (typingIndicator) return;
    
    typingIndicator = document.createElement('div');
    typingIndicator.className = 'typing-indicator';
    typingIndicator.style.display = 'flex';
    typingIndicator.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div>
            <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
            <div style="font-size: 0.8rem; color: #6c757d;">입력 중...</div>
        </div>
    `;
    
    chatContainer.appendChild(typingIndicator);
    scrollToBottom();
}

function hideTypingIndicator() {
    if (typingIndicator) {
        typingIndicator.remove();
        typingIndicator = null;
    }
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function insertCommand(command) {
    // 전달받은 명령어를 그대로 사용
    console.log('삽입할 명령어:', command);
    
    messageInput.value = command;
    messageInput.focus();
}

function forceClearInput() {
    // 강제로 입력창 완전 클리어
    console.log('강제 입력창 클리어 시작');
    
    messageInput.value = '';
    messageInput.blur();
    
    // 모든 상태 초기화
    isComposing = false;
    
    // DOM 조작으로 확실히 클리어
    setTimeout(() => {
        messageInput.value = '';
        messageInput.focus();
        console.log('강제 클리어 완료');
    }, 20);
}

// 전송 상태 안전하게 재설정
function resetSendingState() {
    console.log('전송 상태 재설정');
    isSending = false;
    sendButton.disabled = false;
    sendButton.textContent = '전송';
    hideTypingIndicator();
}

function sendMessage() {
    console.log('sendMessage 호출됨, isSending:', isSending);
    
    // 이미 전송 중이면 무시
    if (isSending) {
        console.log('이미 전송 중이므로 무시');
        return;
    }
    
    const message = messageInput.value.trim();
    console.log('전송할 메시지:', message);
    
    // 빈 메시지 체크
    if (!message) {
        console.log('빈 메시지이므로 무시');
        return;
    }
    
    // 세션 ID 체크
    if (!sessionId) {
        console.log('세션 ID가 없어서 전송 불가');
        addAssistantMessage({ response: '세션이 연결되지 않았습니다. 페이지를 새로고침 해주세요.' });
        return;
    }
    
    // 전송 시작
    isSending = true;
    sendButton.disabled = true;
    sendButton.textContent = '전송 중...';
    
    addUserMessage(message);
    showTypingIndicator();
    
    // 강제 입력창 클리어
    forceClearInput();
    autoResize();
    
    // SSE는 단방향이므로 HTTP POST로 메시지 전송
    fetch('/api/v3/chat/send', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            message: message,
            session_id: sessionId
        })
    })
    .then(response => response.json())
    .then(result => {
        console.log('메시지 전송 완료:', result);
        if (!result.success) {
            console.error('메시지 전송 실패:', result);
            hideTypingIndicator();
            addAssistantMessage({ response: `전송 실패: ${result.error || '알 수 없는 오류'}` });
            resetSendingState();
        }
        // 성공시에는 SSE를 통해 응답이 올 것이므로 여기서는 아무것도 하지 않음
    })
    .catch(error => {
        console.error('메시지 전송 오류:', error);
        hideTypingIndicator();
        addAssistantMessage({ response: `전송 오류: ${error.message}` });
        resetSendingState();
    });
    
    // 타임아웃 안전장치 (20초로 단축)
    setTimeout(() => {
        if (isSending) {
            console.log('타임아웃으로 전송 상태 재설정');
            resetSendingState();
            addAssistantMessage({ response: '응답 시간이 초과되었습니다. 다시 시도해 주세요.' });
        }
    }, 20000);
}

function autoResize() {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
}

// marked.js 로드 확인
document.addEventListener('DOMContentLoaded', function() {
    console.log('marked.js 사용 가능:', typeof marked !== 'undefined');
    if (typeof marked !== 'undefined') {
        console.log('marked 버전:', marked.VERSION || 'unknown');
    }
}); 
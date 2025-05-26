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
let currentReActContainer = null; // ReAct 과정 컨테이너 추적
let currentRequestReActMode = false; // 현재 요청의 ReAct 모드 상태 추적
let timeoutId = null; // 타임아웃 ID 저장

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
                    // ReAct 모드일 때만 ReAct 단계별 메시지를 UI에 표시
                    if (currentRequestReActMode) {
                        handleReActStep(data);
                    }
                    
                    // observing 메시지 중 도구 결과인 경우 처리 (ReAct 모드와 관계없이)
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
    // ReAct 최종 답변 스트리밍인 경우
    if (data.metadata && data.metadata.react_final) {
        if (!currentPartialMessage) {
            // ReAct 컨테이너 종료 (더 이상 단계 추가 안함)
            currentReActContainer = null;
            
            // 새로운 스트리밍 메시지 시작
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
            scrollToBottom();
        }
        
        // 스트리밍 내용 업데이트
        const contentDiv = currentPartialMessage.querySelector('.streaming-content');
        if (contentDiv) {
            contentDiv.innerHTML = renderMarkdown(data.content || '');
            scrollToBottom();
        }
        return;
    }
    
    // 일반 스트리밍 처리
    if (!currentPartialMessage) {
        // 기존 도구 호출 컨테이너가 있으면 재사용
        if (currentToolCallsContainer) {
            // 기존 도구 호출 메시지에 응답 내용 추가
            const parentMessage = currentToolCallsContainer.closest('.message');
            if (parentMessage) {
                // 스트리밍 컨텐츠 영역 추가
                const streamingDiv = document.createElement('div');
                streamingDiv.className = 'streaming-content';
                streamingDiv.innerHTML = renderMarkdown(data.content || '');
                
                // 도구 호출 컨테이너 다음에 응답 추가
                currentToolCallsContainer.insertAdjacentElement('afterend', streamingDiv);
                
                // 현재 부분 메시지로 설정 (스트리밍 계속을 위해)
                currentPartialMessage = parentMessage;
                parentMessage.classList.add('streaming');
                
                scrollToBottom();
                return;
            }
        }
        
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
        // 기존 도구 호출 컨테이너가 있으면 재사용
        if (currentToolCallsContainer) {
            const parentMessage = currentToolCallsContainer.closest('.message');
            if (parentMessage) {
                // 최종 응답 내용 추가
                const responseDiv = document.createElement('div');
                responseDiv.innerHTML = renderMarkdown(data.content || '');
                
                // 도구 호출 컨테이너 다음에 응답 추가
                currentToolCallsContainer.insertAdjacentElement('afterend', responseDiv);
                
                // 도구 호출 컨테이너 초기화
                currentToolCallsContainer = null;
                
                scrollToBottom();
                return;
            }
        }
        
        // 새로운 최종 응답 메시지 (스트리밍 없이)
        hideTypingIndicator();
        addAssistantMessage({ response: data.content });
    }
    
    // ReAct 최종 답변인 경우 ReAct 컨테이너 종료
    if (data.metadata && data.metadata.react_final) {
        currentReActContainer = null;
    }
    
    // 도구 호출 컨테이너 초기화
    currentToolCallsContainer = null;
    
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
    console.log('도구 결과 처리:', data);
    
    if (currentToolCallsContainer) {
        // 서버에서 보내는 데이터 구조에 맞게 수정
        const observationData = data.metadata.observation_data;
        const toolName = observationData.tool;
        const success = observationData.success;
        
        // 기존 도구 호출 박스 찾기 (가장 최근에 추가된 executing 상태의 박스)
        const executingToolCall = currentToolCallsContainer.querySelector('.tool-call.executing');
        
        if (executingToolCall) {
            // 실행 중 상태를 완료 상태로 변경
            executingToolCall.classList.remove('executing');
            executingToolCall.classList.add(success ? 'success' : 'failed');
            
            // 결과 내용 추출 (서버에서 "도구 실행 결과: " 접두사 제거)
            const resultText = data.content.replace('도구 실행 결과: ', '');
            
            // 도구 호출 박스 내용 업데이트 (한 줄로 표시)
            executingToolCall.innerHTML = `
                🔧 ${executingToolCall.getAttribute('data-server')}.${executingToolCall.getAttribute('data-tool')}() 
                ${success ? '✅' : '❌'} ${escapeHtml(resultText)}
            `;
        } else {
            // 기존 박스를 찾지 못한 경우 새로 생성 (fallback)
            const resultElement = document.createElement('div');
            resultElement.className = `tool-call ${success ? 'success' : 'failed'}`;
            
            const resultText = data.content.replace('도구 실행 결과: ', '');
            resultElement.innerHTML = `
                🔧 ${toolName}() ${success ? '✅' : '❌'} ${escapeHtml(resultText)}
            `;
            
            currentToolCallsContainer.appendChild(resultElement);
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
    
    // ReAct 모드 상태 초기화
    currentRequestReActMode = false;
    
    // 타임아웃 취소
    if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
    }
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
    
    // ReAct 모드 체크
    const reactModeToggle = document.getElementById('reactModeToggle');
    const reactMode = reactModeToggle ? reactModeToggle.checked : false;
    console.log('ReAct 모드:', reactMode);
    
    // 현재 요청의 ReAct 모드 상태 저장
    currentRequestReActMode = reactMode;
    
    // 전송 시작
    isSending = true;
    sendButton.disabled = true;
    sendButton.textContent = '전송 중...';
    
    addUserMessage(message);
    showTypingIndicator();
    
    // ReAct 컨테이너 초기화 (새로운 요청 시작)
    currentReActContainer = null;
    
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
            session_id: sessionId,
            react_mode: reactMode  // ReAct 모드 포함
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
    timeoutId = setTimeout(() => {
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

// ReAct 단계별 메시지 처리
function handleReActStep(data) {
    console.log('ReAct 단계 처리:', data.type, data.content);
    
    // ReAct 컨테이너가 없으면 새로 생성
    if (!currentReActContainer) {
        hideTypingIndicator(); // 타이핑 인디케이터 숨기기
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant react-container';
        messageDiv.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <div class="react-header">
                    <span class="react-title">🧠 ReAct 사고 과정</span>
                    <span class="react-time">${new Date().toLocaleTimeString()}</span>
                </div>
                <div class="react-steps"></div>
            </div>
        `;
        
        chatContainer.appendChild(messageDiv);
        currentReActContainer = messageDiv.querySelector('.react-steps');
        scrollToBottom();
    }
    
    let stepIcon = '';
    let stepClass = '';
    let stepTitle = '';
    
    switch (data.type) {
        case 'thinking':
            stepIcon = '🤔';
            stepClass = 'react-thinking';
            stepTitle = '사고';
            break;
        case 'acting':
            stepIcon = '⚡';
            stepClass = 'react-acting';
            stepTitle = '행동';
            break;
        case 'observing':
            stepIcon = '👁️';
            stepClass = 'react-observing';
            stepTitle = '관찰';
            break;
    }
    
    const iteration = data.metadata?.iteration || '';
    const iterationText = iteration ? ` ${iteration}` : '';
    
    // acting 단계에서 도구 호출 정보 추출
    let toolCallInfo = '';
    if (data.type === 'acting' && data.content) {
        const toolMatch = data.content.match(/행동 실행 중:\s*(.+)/);
        if (toolMatch) {
            const actionText = toolMatch[1];
            const toolPattern = /(\w+):\s*(.+)/;
            const toolMatchResult = actionText.match(toolPattern);
            
            if (toolMatchResult) {
                const toolName = toolMatchResult[1];
                const toolArgs = toolMatchResult[2];
                toolCallInfo = ` → 🔧 ${toolName}(${escapeHtml(toolArgs)})`;
            }
        }
    }
    
    // observing 단계에서 도구 결과 정보 추출
    let toolResultInfo = '';
    if (data.type === 'observing' && data.content) {
        const successMatch = data.content.match(/도구 '(\w+)' 실행 성공:\s*(.+)/);
        const failMatch = data.content.match(/도구 '(\w+)' 실행 실패:\s*(.+)/);
        
        if (successMatch) {
            const result = successMatch[2];
            toolResultInfo = ` → ✅ ${escapeHtml(result)}`;
        } else if (failMatch) {
            const error = failMatch[2];
            toolResultInfo = ` → ❌ ${escapeHtml(error)}`;
        }
    }
    
    // 단계 요소 생성
    const stepDiv = document.createElement('div');
    stepDiv.className = `react-step-item ${stepClass}`;
    
    // 사고 과정의 경우 내용을 간략하게 표시
    let displayContent = data.content;
    if (data.type === 'thinking' && data.content.includes('사고:')) {
        const thoughtMatch = data.content.match(/사고:\s*(.+)/);
        if (thoughtMatch) {
            displayContent = thoughtMatch[1].substring(0, 100) + (thoughtMatch[1].length > 100 ? '...' : '');
        }
    }
    
    stepDiv.innerHTML = `
        <span class="step-icon">${stepIcon}</span>
        <span class="step-title">${stepTitle}${iterationText}:</span>
        <span class="step-content">${escapeHtml(displayContent)}${toolCallInfo}${toolResultInfo}</span>
    `;
    
    currentReActContainer.appendChild(stepDiv);
    scrollToBottom();
} 
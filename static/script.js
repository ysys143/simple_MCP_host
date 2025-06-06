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
let isPhoenixLinkActivatedByChat = false; // Phoenix UI 링크 활성화 상태 추적 (채팅 기반)
let currentReActStepsContainer = null; // ReAct 단계 컨테이너 추적
let currentStepIndex = 1; // 현재 단계 인덱스
let isRespondingToUser = false; // 사용자 응답 상태 추적

// 재연결 관리 변수들 추가
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let baseReconnectDelay = 3000; // 3초
let maxReconnectDelay = 60000; // 60초
let reconnectTimeoutId = null;
let isManualDisconnect = false;
let isPageVisible = true;

// 페이지 가시성 API 설정
document.addEventListener('visibilitychange', function() {
    isPageVisible = !document.hidden;
    
    if (document.hidden) {
        console.log('페이지가 비활성화됨 - SSE 연결 일시 중단');
        // 페이지가 숨겨지면 재연결 시도 중단
        if (reconnectTimeoutId) {
            clearTimeout(reconnectTimeoutId);
            reconnectTimeoutId = null;
        }
    } else {
        console.log('페이지가 활성화됨 - SSE 연결 재시도');
        // 페이지가 다시 보이면 연결되지 않은 경우 재연결 시도
        if (!isConnected && !isManualDisconnect) {
            scheduleReconnect();
        }
    }
});

// 지수 백오프를 적용한 재연결 스케줄링
function scheduleReconnect() {
    // 페이지가 비활성화되어 있거나 수동 연결 해제 상태면 재연결하지 않음
    if (!isPageVisible || isManualDisconnect) {
        console.log('재연결 조건 불충족 - 페이지 비활성화 또는 수동 해제');
        return;
    }
    
    // 최대 재연결 시도 횟수 초과 확인
    if (reconnectAttempts >= maxReconnectAttempts) {
        console.log(`최대 재연결 시도 횟수 초과 (${maxReconnectAttempts}회)`);
        updateConnectionStatus('failed', '🔴 연결 실패 (재시도 한계 초과)');
        return;
    }
    
    // 지수 백오프 계산
    const delay = Math.min(baseReconnectDelay * Math.pow(2, reconnectAttempts), maxReconnectDelay);
    reconnectAttempts++;
    
    console.log(`재연결 시도 ${reconnectAttempts}/${maxReconnectAttempts} - ${delay}ms 후 재시도`);
    updateConnectionStatus('reconnecting', `🟡 재연결 중... (${reconnectAttempts}/${maxReconnectAttempts})`);
    
    // 기존 타이머 정리
    if (reconnectTimeoutId) {
        clearTimeout(reconnectTimeoutId);
    }
    
    reconnectTimeoutId = setTimeout(() => {
        reconnectTimeoutId = null;
        connect();
    }, delay);
}

// 재연결 상태 초기화
function resetReconnectState() {
    reconnectAttempts = 0;
    if (reconnectTimeoutId) {
        clearTimeout(reconnectTimeoutId);
        reconnectTimeoutId = null;
    }
}

function generateSessionId() {
    // 탭별 고유 식별자 추가
    const tabId = Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    return `web_${tabId}_${Date.now()}`;
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
            
            // 연결 성공 시 재연결 상태 초기화
            resetReconnectState();
            isManualDisconnect = false;
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
            
            // 수동 연결 해제가 아닌 경우에만 재연결 시도
            if (!isManualDisconnect) {
                scheduleReconnect();
            }
        };
        
    } catch (error) {
        console.error('연결 시도 중 오류:', error);
        updateConnectionStatus('disconnected', '🔴 연결 오류');
        
        // 연결 시도 중 오류 발생 시에도 재연결 시도
        if (!isManualDisconnect) {
            scheduleReconnect();
        }
    }
}

function handlePartialResponse(data) {
    // ReAct 최종 답변 스트리밍인 경우
    if (data.metadata && data.metadata.react_final) {
        if (!currentPartialMessage) {
            // 새로운 ReAct 최종 답변 메시지 시작
            hideTypingIndicator();
            
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message assistant streaming react-final';
            messageDiv.innerHTML = `
                <div class="message-avatar">🤖</div>
                <div class="message-content">
                    <div class="react-label">💭 최종 답변</div>
                    <div class="streaming-content"></div>
                    <div class="message-time">${new Date().toLocaleTimeString()}</div>
                </div>
            `;
            
            chatContainer.appendChild(messageDiv);
            currentPartialMessage = messageDiv;
            // 스트리밍 텍스트 저장용 속성 추가
            currentPartialMessage.streamingText = '';
            scrollToBottom();
        }
        
        // ReAct 최종 답변 업데이트
        const contentDiv = currentPartialMessage.querySelector('.streaming-content');
        if (contentDiv) {
            // 단어 단위 스트리밍 처리
            if (data.metadata && data.metadata.word_streaming) {
                // 새로운 단어를 텍스트로 누적 (마크다운 렌더링 없이)
                const newWord = data.content || '';
                currentPartialMessage.streamingText += newWord;
                
                // 단순히 텍스트로 표시 (줄바꿈만 <br>로 변환)
                const displayText = escapeHtml(currentPartialMessage.streamingText).replace(/\n/g, '<br>');
                contentDiv.innerHTML = displayText;
                
                console.log(`ReAct 단어 추가: "${newWord}"`);
            } else {
                // 전체 텍스트 교체 (기존 방식)
                contentDiv.innerHTML = renderMarkdown(data.content || '');
            }
        }
        
        scrollToBottom();
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
                
                // 단어 단위 처리
                if (data.metadata && data.metadata.word_streaming) {
                    const displayText = escapeHtml(data.content || '').replace(/\n/g, '<br>');
                    streamingDiv.innerHTML = displayText;
                    // 스트리밍 텍스트 저장용 속성 추가
                    parentMessage.streamingText = data.content || '';
                } else {
                    streamingDiv.innerHTML = renderMarkdown(data.content || '');
                }
                
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
        // 스트리밍 텍스트 저장용 속성 추가
        currentPartialMessage.streamingText = '';
        
        // 도구 호출 컨테이너 초기화 (새로운 응답 시작)
        currentToolCallsContainer = null;
        
        scrollToBottom();
    }
    
    // 스트리밍 내용 업데이트
    const contentDiv = currentPartialMessage.querySelector('.streaming-content');
    if (contentDiv) {
        // 단어 단위 스트리밍 처리 (텍스트만 누적)
        if (data.metadata && data.metadata.word_streaming) {
            // 새로운 단어를 텍스트로 누적 (마크다운 렌더링 없이)
            const newWord = data.content || '';
            currentPartialMessage.streamingText += newWord;
            
            // 단순히 텍스트로 표시 (줄바꿈만 <br>로 변환)
            const displayText = escapeHtml(currentPartialMessage.streamingText).replace(/\n/g, '<br>');
            contentDiv.innerHTML = displayText;
            
            console.log(`단어 추가: "${newWord}" (총 길이: ${currentPartialMessage.streamingText.length})`);
        } else {
            // 전체 텍스트 교체 (기존 방식)
            contentDiv.innerHTML = renderMarkdown(data.content || '');
        }
    }
    
    scrollToBottom();
}

function handleFinalResponse(data) {
    console.log('[handleFinalResponse] Received final response. Data:', data);
    if (currentPartialMessage) {
        // 기존 스트리밍 메시지를 최종 응답으로 변경
        currentPartialMessage.className = 'message assistant';
        const contentDiv = currentPartialMessage.querySelector('.streaming-content');
        if (contentDiv) {
            // 스트리밍 중에 누적된 텍스트가 있으면 그것을 마크다운으로 렌더링
            if (currentPartialMessage.streamingText) {
                contentDiv.innerHTML = renderMarkdown(currentPartialMessage.streamingText);
                console.log('스트리밍 완료 - 마크다운 렌더링 적용');
            } else {
                // 스트리밍 텍스트가 없으면 서버에서 온 최종 응답 사용
                contentDiv.innerHTML = renderMarkdown(data.content || '');
            }
        }
        // 스트리밍 텍스트 정리
        delete currentPartialMessage.streamingText;
        currentPartialMessage = null;
    } else {
        // 기존 도구 호출 컨테이너가 있으면 재사용
        if (currentToolCallsContainer) {
            const parentMessage = currentToolCallsContainer.closest('.message');
            if (parentMessage) {
                // 최종 응답 내용 추가
                const responseDiv = document.createElement('div');
                
                // 스트리밍 중에 누적된 텍스트가 있으면 그것을 사용
                if (parentMessage.streamingText) {
                    responseDiv.innerHTML = renderMarkdown(parentMessage.streamingText);
                    delete parentMessage.streamingText;
                } else {
                    responseDiv.innerHTML = renderMarkdown(data.content || '');
                }
                
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
        if (currentReActContainer) {
            currentReActContainer.classList.remove('streaming');
            currentReActContainer = null;
        }
        currentRequestReActMode = false; // ReAct 모드 상태 초기화
    }
    
    // 도구 호출 컨테이너 초기화
    currentToolCallsContainer = null;
    
    scrollToBottom();

    // 최종 응답 수신 시 Phoenix UI 링크 활성화 시도
    console.log('[handleFinalResponse] Attempting to activate Phoenix UI link...');
    activatePhoenixUILinkAfterChat();
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
    
    // 서버명과 도구명 정보
    const server = data.metadata?.server || 'unknown';
    const tool = data.metadata?.tool || 'unknown';
    const arguments = data.metadata?.arguments || {};
    
    // JSON-RPC 요청 형태로 구성
    const jsonRpcRequest = {
        "jsonrpc": "2.0",
        "id": Date.now(), // 간단한 ID 생성
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": arguments
        }
    };
    
    // JSON을 보기 좋게 포맷팅
    const formattedRequest = JSON.stringify(jsonRpcRequest, null, 2);
    
    // 도구 호출 박스 추가
    const toolCallDiv = document.createElement('div');
    toolCallDiv.className = 'tool-call executing';
    toolCallDiv.setAttribute('data-server', server);
    toolCallDiv.setAttribute('data-tool', tool);
    toolCallDiv.setAttribute('data-id', jsonRpcRequest.id);
    
    toolCallDiv.innerHTML = `
        <div style="font-weight: bold; margin-bottom: 8px;">🔧 MCP 도구 호출 요청 (서버: ${server})</div>
        ${createCollapsibleJson(formattedRequest, 'JSON-RPC 요청')}
        <div class="tool-status" style="margin-top: 8px;">⏳ 실행 중...</div>
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
            let resultText = data.content.replace('도구 실행 결과: ', '');
            
            // 요청 ID 가져오기
            const requestId = executingToolCall.getAttribute('data-id') || Date.now();
            
            // JSON-RPC 응답 형태로 구성
            const jsonRpcResponse = {
                "jsonrpc": "2.0",
                "id": parseInt(requestId),
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": resultText
                        }
                    ]
                }
            };
            
            // 에러인 경우 error 필드 사용
            if (!success) {
                delete jsonRpcResponse.result;
                jsonRpcResponse.error = {
                    "code": -1,
                    "message": "Tool execution failed",
                    "data": resultText
                };
            }
            
            // JSON을 보기 좋게 포맷팅
            const formattedResponse = JSON.stringify(jsonRpcResponse, null, 2);
            
            // 기존 내용에서 "⏳ 실행 중..." 부분을 응답으로 교체
            const currentContent = executingToolCall.innerHTML;
            const updatedContent = currentContent.replace(
                '<div class="tool-status" style="margin-top: 8px;">⏳ 실행 중...</div>',
                `<div style="font-weight: bold; margin: 8px 0;">📤 MCP 도구 호출 응답</div>
                ${createCollapsibleJson(formattedResponse, 'JSON-RPC 응답')}`
            );
            
            executingToolCall.innerHTML = updatedContent;
        } else {
            // 기존 박스를 찾지 못한 경우 새로 생성 (fallback)
            const resultElement = document.createElement('div');
            resultElement.className = `tool-call ${success ? 'success' : 'failed'}`;
            
            let resultText = data.content.replace('도구 실행 결과: ', '');
            
            // JSON-RPC 응답 형태로 구성
            const jsonRpcResponse = {
                "jsonrpc": "2.0",
                "id": Date.now(),
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": resultText
                        }
                    ]
                }
            };
            
            if (!success) {
                delete jsonRpcResponse.result;
                jsonRpcResponse.error = {
                    "code": -1,
                    "message": "Tool execution failed",
                    "data": resultText
                };
            }
            
            const formattedResponse = JSON.stringify(jsonRpcResponse, null, 2);
            
            resultElement.innerHTML = `
                <div style="font-weight: bold; margin-bottom: 8px;">📤 MCP 도구 호출 응답 (도구: ${toolName})</div>
                ${createCollapsibleJson(formattedResponse, 'JSON-RPC 응답')}
            `;
            
            currentToolCallsContainer.appendChild(resultElement);
        }
        
        scrollToBottom();
    }
}

function updateConnectionStatus(status, text) {
    if (connectionStatus) {
        connectionStatus.textContent = text;
        connectionStatus.className = `status ${status}`;
        isConnected = (status === 'connected');
        
        // 수동 연결/해제 버튼 표시 제어
        const manualConnectBtn = document.getElementById('manualConnectBtn');
        
        if (manualConnectBtn) {
            if (status === 'connected') {
                manualConnectBtn.style.display = 'none';
            } else if (status === 'failed' || status === 'disconnected') {
                manualConnectBtn.style.display = 'inline-block';
            } else {
                // 연결 중이거나 재연결 중일 때는 숨김
                manualConnectBtn.style.display = 'none';
            }
        }
        
        console.log('연결 상태 업데이트:', status, text);
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

function createCollapsibleJson(jsonString, title, isSmall = false) {
    /**
     * JSON 문자열을 접었다 폈다 할 수 있는 HTML로 변환
     * @param {string} jsonString - JSON 문자열
     * @param {string} title - 헤더에 표시할 제목
     * @param {boolean} isSmall - 작은 JSON인지 여부 (3줄 이하)
     * @returns {string} HTML 문자열
     */
    const escapedJson = escapeHtml(jsonString);
    const lines = jsonString.split('\n').length;
    
    // 3줄 이하의 작은 JSON은 접기 기능 없이 표시
    if (lines <= 3 || isSmall) {
        return `
            <div class="json-small">
                <pre>${escapedJson}</pre>
            </div>
        `;
    }
    
    // 큰 JSON은 접기 기능과 함께 표시 (기본적으로 접힌 상태)
    const uniqueId = 'json_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    
    return `
        <div class="json-collapsible">
            <div class="json-header collapsed" onclick="toggleJsonCollapse('${uniqueId}')">
                <span>${title}</span>
                <span class="toggle-icon">▼</span>
            </div>
            <div class="json-content collapsed" id="${uniqueId}">
                <pre>${escapedJson}</pre>
            </div>
        </div>
    `;
}

function toggleJsonCollapse(elementId) {
    /**
     * JSON 블록의 접기/펼치기 상태를 토글
     * @param {string} elementId - 토글할 요소의 ID
     */
    const content = document.getElementById(elementId);
    const header = content.previousElementSibling;
    
    if (content.classList.contains('collapsed')) {
        // 펼치기
        content.classList.remove('collapsed');
        header.classList.remove('collapsed');
    } else {
        // 접기
        content.classList.add('collapsed');
        header.classList.add('collapsed');
    }
}

// 전역 스코프에서 접근 가능하도록 설정
window.toggleJsonCollapse = toggleJsonCollapse;

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
    console.log("타이핑 인디케이터 표시 시도");
    if (typingIndicator && chatContainer.contains(typingIndicator)) {
        console.log("타이핑 인디케이터 이미 존재함");
        return; // 이미 존재하면 아무것도 하지 않음
    }

    typingIndicator = document.createElement('div');
    typingIndicator.className = 'message assistant typing-indicator';
    typingIndicator.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="dot-flashing"></div>
        </div>
    `;
    chatContainer.appendChild(typingIndicator);
    console.log("타이핑 인디케이터 추가됨");
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
    
    // 사용자 메시지 전송 시 Phoenix UI 링크 활성화 시도
    console.log('[sendMessage] Attempting to activate Phoenix UI link...');
    activatePhoenixUILinkAfterChat();
    
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
    
    // 타임아웃 안전장치 (120초)
    timeoutId = setTimeout(() => {
        if (isSending) {
            console.log('타임아웃으로 전송 상태 재설정');
            resetSendingState();
            addAssistantMessage({ response: '응답 시간이 초과되었습니다. 다시 시도해 주세요.' });
        }
    }, 120000);
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
    console.log('ReAct 단계 처리:', data.type, data.content, data.action_details, data.observation_data);
    
    if (!currentReActContainer) {
        hideTypingIndicator();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant react-container';
        messageDiv.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <div class="react-header">
                    <span class="react-title">🧠 ReAct 사고 과정</span>
                    <span class="react-time">${new Date().toLocaleTimeString()}</span>
                </div>
                <div class="react-steps-container"></div>
            </div>
        `;
        chatContainer.appendChild(messageDiv);
        currentReActContainer = messageDiv;
        currentReActStepsContainer = messageDiv.querySelector('.react-steps-container');
        currentStepIndex = 1;
        if (isRespondingToUser) {
            isRespondingToUser = false;
        }
    }

    const timestamp = new Date().toLocaleTimeString(); // 이 변수는 이제 UI 표시에는 직접 사용되지 않음

    if (data.type === 'thinking') {
        const stepDiv = document.createElement('div');
        stepDiv.className = `react-step react-thinking react-step-${currentStepIndex}`;
        stepDiv.innerHTML = `
            <div class="react-step-header">
                <span class="react-step-icon">🤔</span>
                <span class="react-step-title">생각하는 중...</span>
            </div>
            <div class="react-step-content"><p>${escapeHtml(data.content)}</p></div>
        `;
        currentReActStepsContainer.appendChild(stepDiv);
        currentStepIndex++;
    } else if (data.type === 'acting') {
        const stepDiv = document.createElement('div');
        stepDiv.className = `react-step react-acting react-step-${currentStepIndex}`;
        
        let actingContentHtml = `
            <div class="react-step-header">
                <span class="react-step-icon">🚀</span>
                <span class="react-step-title">행동 실행 중: ${escapeHtml(data.content)}</span>
            </div>
            <div class="react-step-content">
                <p>도구를 호출하고 있습니다...</p>
            </div>
        `;
        stepDiv.innerHTML = actingContentHtml;
        currentReActStepsContainer.appendChild(stepDiv);
        currentStepIndex++;
    } else if (data.type === 'observing') {
        const stepDiv = document.createElement('div');
        stepDiv.className = `react-step react-observing react-step-${currentStepIndex}`;

        const observationData = data.metadata?.observation_data || data.observation_data;
        const actualRequestJson = observationData?.actual_mcp_request_json;
        const actualResponseJson = observationData?.actual_mcp_response_json;
        
        const toolNameFromObservation = actualRequestJson ? JSON.parse(actualRequestJson).params.name : "알 수 없는 도구";

        // 일반 모드와 동일한 tool-call 스타일 사용
        let toolCallHtml = '';
        
        // 1. MCP 도구 호출 요청
        if (actualRequestJson) {
            const formattedRequestJson = JSON.stringify(JSON.parse(actualRequestJson), null, 2);
            toolCallHtml += `
                <div class="tool-call success">
                    <div style="font-weight: bold; margin-bottom: 8px;">🔧 MCP 도구 호출 요청 (서버: weather)</div>
                    ${createCollapsibleJson(formattedRequestJson, 'JSON-RPC 요청')}
                </div>
            `;
        }
        
        // 2. MCP 도구 호출 응답
        if (actualResponseJson) {
            const formattedResponseJson = JSON.stringify(JSON.parse(actualResponseJson), null, 2);
            toolCallHtml += `
                <div class="tool-call success">
                    <div style="font-weight: bold; margin-bottom: 8px;">📤 MCP 도구 호출 응답</div>
                    ${createCollapsibleJson(formattedResponseJson, 'JSON-RPC 응답')}
                </div>
            `;
        }
        
        // 3. 관찰 결과
        const observationText = `<div class="react-observation-text">${renderMarkdown(data.content)}</div>`;

        stepDiv.innerHTML = `
            <div class="react-step-header">
                <span class="react-step-icon">👀</span>
                <span class="react-step-title">관찰</span>
            </div>
            <div class="react-step-content">
                ${toolCallHtml}
                ${observationText}
            </div>
        `;
        currentReActStepsContainer.appendChild(stepDiv);
        currentStepIndex++;
    }

    scrollToBottom();
}

// Phoenix UI 링크 활성화 함수 (채팅 기반)
function activatePhoenixUILinkAfterChat() {
    console.log('[activatePhoenixUILinkAfterChat] Function called.');
    if (isPhoenixLinkActivatedByChat) {
        // console.log('[activatePhoenixUILinkAfterChat] Link already activated by chat. Skipping.'); // 너무 빈번한 로그라 주석 처리
        return; // 이미 활성화되었으면 중복 실행 방지
    }

    const phoenixUILink = document.getElementById('phoenixUILink');
    if (phoenixUILink) {
        // console.log('[activatePhoenixUILinkAfterChat] Phoenix UI link element found.'); // 너무 빈번한 로그라 주석 처리
        // console.log('[activatePhoenixUILinkAfterChat] Current display style:', phoenixUILink.style.display); // 너무 빈번한 로그라 주석 처리
        // console.log('[activatePhoenixUILinkAfterChat] Current classList before change:', phoenixUILink.classList.toString()); // 너무 빈번한 로그라 주석 처리

        // 서버 설정에 의해 Phoenix UI가 활성화된 경우에만 채팅 기반 활성화 로직 적용
        // (기존 /api/config fetch 로직은 그대로 유지되며, 그 결과에 따라 기본 display 상태가 결정됨)
        // 여기서 하는 일은 채팅이 시작되면 .phoenix-link-inactive 클래스만 제거하는 것.
        if (phoenixUILink.style.display !== 'none') { // 링크가 숨겨져 있지 않은 경우에만 (서버 설정에 의해 활성화된 경우)
            phoenixUILink.classList.remove('phoenix-link-inactive');
            isPhoenixLinkActivatedByChat = true;
            console.log('[activatePhoenixUILinkAfterChat] "phoenix-link-inactive" class removed.');
            // console.log('[activatePhoenixUILinkAfterChat] isPhoenixLinkActivatedByChat set to true.'); // 너무 빈번한 로그라 주석 처리
            // console.log('[activatePhoenixUILinkAfterChat] Current classList after change:', phoenixUILink.classList.toString()); // 너무 빈번한 로그라 주석 처리
        } else {
            // console.log('[activatePhoenixUILinkAfterChat] Link is hidden (display: none), not activating.'); // 너무 빈번한 로그라 주석 처리
        }
    } else {
        console.error('[activatePhoenixUILinkAfterChat] Phoenix UI link element NOT found!');
    }
}

// 수동 연결 해제 함수 추가
function disconnect() {
    console.log('수동 SSE 연결 해제');
    isManualDisconnect = true;
    resetReconnectState();
    
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    updateConnectionStatus('disconnected', '🔴 연결 해제됨');
}

// 수동 연결 함수 추가
function manualConnect() {
    console.log('수동 SSE 연결 시도');
    isManualDisconnect = false;
    resetReconnectState();
    connect();
}

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    // 요소 참조 저장
    connectionStatus = document.getElementById('connectionStatus');
    serverCount = document.getElementById('serverCount');
    toolCount = document.getElementById('toolCount');
    chatContainer = document.getElementById('chatContainer');
    messageInput = document.getElementById('messageInput');
    sendButton = document.getElementById('sendButton');
    
    // Phoenix UI 링크 설정
    const phoenixUILink = document.getElementById('phoenixUILink');
    if (phoenixUILink) {
        fetch('/api/config')
            .then(response => response.json())
            .then(config => {
                if (config.is_phoenix_enabled && config.phoenix_base_url) {
                    phoenixUILink.href = config.phoenix_base_url;
                    
                    // (선택 사항) 프로젝트 이름 표시
                    const projectInfo = document.createElement('span');
                    projectInfo.textContent = `(Project: ${config.project_name || 'default'})`;
                    projectInfo.style.fontSize = '0.7rem';
                    projectInfo.style.marginLeft = '8px';
                    projectInfo.style.color = '#bbb';
                    
                    phoenixUILink.appendChild(projectInfo);
                } else {
                    phoenixUILink.style.display = 'none'; 
                }
            })
            .catch(error => {
                console.error('Phoenix 설정을 가져오는 중 오류 발생:', error);
                phoenixUILink.style.display = 'none';
            });
    } else {
        console.warn("Phoenix UI 링크 요소를 찾을 수 없습니다. (ID: phoenixUILink)");
    }
    
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
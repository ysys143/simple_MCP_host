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
                    // phoenixUILink.style.display = 'flex'; // CSS에서 .nav-links가 이미 display:flex를 가짐
                    // HTML에 phoenix-link-inactive 클래스가 이미 적용되어 있으므로, 여기서는 특별히 추가/제거할 필요 없음
                    // 만약 HTML에 없다면 여기서 classList.add('phoenix-link-inactive')를 할 수 있음

                    // (선택 사항) 프로젝트 이름 표시
                    const projectInfo = document.createElement('span');
                    projectInfo.textContent = `(Project: ${config.project_name || 'default'})`;
                    projectInfo.style.fontSize = '0.7rem'; // 로고/메뉴보다 작게
                    projectInfo.style.marginLeft = '8px'; // 링크 텍스트와 간격
                    projectInfo.style.color = '#bbb'; // 약간 흐리게
                    // projectInfo.style.alignSelf = 'center'; // 부모가 flex container가 아니므로 불필요, a 태그의 align-items가 처리
                    
                    phoenixUILink.appendChild(projectInfo); // a 태그의 자식으로 추가

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
    
    // 단계 요소 생성
    const stepDiv = document.createElement('div');
    stepDiv.className = `react-step-item ${stepClass}`;
    
    let stepContent = '';
    
    // acting 단계에서 도구 호출 정보를 JSON-RPC 형태로 표시
    if (data.type === 'acting' && data.content) {
        const toolMatch = data.content.match(/행동 실행 중:\s*(.+)/);
        if (toolMatch) {
            const actionText = toolMatch[1];
            const toolPattern = /(\w+):\s*(.+)/;
            const toolMatchResult = actionText.match(toolPattern);
            
            if (toolMatchResult) {
                const toolName = toolMatchResult[1];
                const toolArgsText = toolMatchResult[2];
                
                // 도구 인수를 파싱하여 JSON 객체로 변환 시도
                let toolArgs = {};
                try {
                    // 간단한 파싱 (예: location="서울" 형태)
                    const argMatches = toolArgsText.match(/(\w+)="([^"]+)"/g);
                    if (argMatches) {
                        argMatches.forEach(match => {
                            const [, key, value] = match.match(/(\w+)="([^"]+)"/);
                            toolArgs[key] = value;
                        });
                    } else {
                        // 파싱 실패시 원본 텍스트 사용
                        toolArgs = { "input": toolArgsText };
                    }
                } catch (e) {
                    toolArgs = { "input": toolArgsText };
                }
                
                // JSON-RPC 요청 형태로 구성
                const jsonRpcRequest = {
                    "jsonrpc": "2.0",
                    "id": Date.now(),
                    "method": "tools/call",
                    "params": {
                        "name": toolName,
                        "arguments": toolArgs
                    }
                };
                
                const formattedRequest = JSON.stringify(jsonRpcRequest, null, 2);
                
                stepContent = `
                    <div style="margin-top: 8px;">
                        <div style="font-weight: bold; margin-bottom: 4px;">🔧 MCP 도구 호출 요청</div>
                        ${createCollapsibleJson(formattedRequest, 'JSON-RPC 요청')}
                    </div>
                `;
            } else {
                stepContent = escapeHtml(data.content);
            }
        } else {
            stepContent = escapeHtml(data.content);
        }
    }
    // observing 단계에서 도구 결과를 JSON-RPC 형태로 표시
    else if (data.type === 'observing' && data.content) {
        const successMatch = data.content.match(/도구 '(\w+)' 실행 성공:\s*(.+)/);
        const failMatch = data.content.match(/도구 '(\w+)' 실행 실패:\s*(.+)/);
        
        if (successMatch || failMatch) {
            const isSuccess = !!successMatch;
            const toolName = isSuccess ? successMatch[1] : failMatch[1];
            const resultText = isSuccess ? successMatch[2] : failMatch[2];
            
            // JSON-RPC 응답 형태로 구성
            const jsonRpcResponse = {
                "jsonrpc": "2.0",
                "id": Date.now(),
            };
            
            if (isSuccess) {
                jsonRpcResponse.result = {
                    "content": [
                        {
                            "type": "text",
                            "text": resultText
                        }
                    ]
                };
            } else {
                jsonRpcResponse.error = {
                    "code": -1,
                    "message": "Tool execution failed",
                    "data": resultText
                };
            }
            
            const formattedResponse = JSON.stringify(jsonRpcResponse, null, 2);
            
            stepContent = `
                <div style="margin-top: 8px;">
                    <div style="font-weight: bold; margin-bottom: 4px;">📤 MCP 도구 호출 응답 (도구: ${toolName})</div>
                    ${createCollapsibleJson(formattedResponse, 'JSON-RPC 응답')}
                </div>
            `;
        } else {
            stepContent = escapeHtml(data.content);
        }
    }
    // thinking 단계는 간략하게 표시
    else if (data.type === 'thinking' && data.content.includes('사고:')) {
        const thoughtMatch = data.content.match(/사고:\s*(.+)/);
        if (thoughtMatch) {
            const thoughtText = thoughtMatch[1];
            stepContent = escapeHtml(thoughtText.substring(0, 100) + (thoughtText.length > 100 ? '...' : ''));
        } else {
            stepContent = escapeHtml(data.content);
        }
    }
    // 기타 단계는 그대로 표시
    else {
        stepContent = escapeHtml(data.content);
    }
    
    stepDiv.innerHTML = `
        <span class="step-icon">${stepIcon}</span>
        <span class="step-title">${stepTitle}:</span>
        <div class="step-content">${stepContent}</div>
    `;
    
    currentReActContainer.appendChild(stepDiv);
    scrollToBottom();
}

// Phoenix UI 링크 활성화 함수 (채팅 기반)
function activatePhoenixUILinkAfterChat() {
    console.log('[activatePhoenixUILinkAfterChat] Function called.');
    if (isPhoenixLinkActivatedByChat) {
        console.log('[activatePhoenixUILinkAfterChat] Link already activated by chat. Skipping.');
        return; // 이미 활성화되었으면 중복 실행 방지
    }

    const phoenixUILink = document.getElementById('phoenixUILink');
    if (phoenixUILink) {
        console.log('[activatePhoenixUILinkAfterChat] Phoenix UI link element found.');
        console.log('[activatePhoenixUILinkAfterChat] Current display style:', phoenixUILink.style.display);
        console.log('[activatePhoenixUILinkAfterChat] Current classList before change:', phoenixUILink.classList.toString());

        // 서버 설정에 의해 Phoenix UI가 활성화된 경우에만 채팅 기반 활성화 로직 적용
        // (기존 /api/config fetch 로직은 그대로 유지되며, 그 결과에 따라 기본 display 상태가 결정됨)
        // 여기서 하는 일은 채팅이 시작되면 .phoenix-link-inactive 클래스만 제거하는 것.
        if (phoenixUILink.style.display !== 'none') { // 링크가 숨겨져 있지 않은 경우에만 (서버 설정에 의해 활성화된 경우)
            phoenixUILink.classList.remove('phoenix-link-inactive');
            isPhoenixLinkActivatedByChat = true;
            console.log('[activatePhoenixUILinkAfterChat] "phoenix-link-inactive" class removed.');
            console.log('[activatePhoenixUILinkAfterChat] isPhoenixLinkActivatedByChat set to true.');
            console.log('[activatePhoenixUILinkAfterChat] Current classList after change:', phoenixUILink.classList.toString());
        } else {
            console.log('[activatePhoenixUILinkAfterChat] Link is hidden (display: none), not activating.');
        }
    } else {
        console.error('[activatePhoenixUILinkAfterChat] Phoenix UI link element NOT found!');
    }
} 
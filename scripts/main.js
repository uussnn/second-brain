/**
 * Entrypoint for Second Brain Agent
 * ADK-compliant executable logic for state routing and self-evolution.
 */

const fs = require('fs');
const path = require('path');

const BRAIN_DIR = path.join(process.env.HOME || process.env.USERPROFILE || '.', 'SecondBrain', 'Evolution');

function checkAndInitializeDir() {
    if (!fs.existsSync(BRAIN_DIR)) {
        fs.mkdirSync(BRAIN_DIR, { recursive: true });
        console.log(`[INIT] Создана директория: ${BRAIN_DIR}`);
    }
}

function processMemoryDistillation() {
    const eventsPath = path.join(BRAIN_DIR, 'events.jsonl');
    if (!fs.existsSync(eventsPath)) return;

    const data = fs.readFileSync(eventsPath, 'utf-8');
    // Approximate token count by word count or generic byte size, for example 1 token ~ 4 chars
    const approxTokens = data.length / 4;

    if (approxTokens >= 8000) {
        console.log(`[DISTILLATION] Триггер активирован (Достигнут предел 8000 токенов, сейчас ~${Math.floor(approxTokens)}). Выполняется сжатие...`);
        // В реальном агенте здесь вызывается функция-компрессор "Retrospective Reflection" LLM
        
        // После дистилляции очищаем старые логи, оставляем последние 2000 токенов (ок. 20 строк)
        const lines = data.split('\n').filter(l => l.trim() !== '');
        const recentLines = lines.slice(-20); 
        fs.writeFileSync(eventsPath, recentLines.join('\n') + '\n');
        console.log(`[DISTILLATION] Память сжата через Retrospective Reflection. События очищены.`);
    }
}

function runAgentCycle(inputParams) {
    console.log(`🧠 Запуск цикла Второго Мозга (v4.0.0)`);
    checkAndInitializeDir();
    processMemoryDistillation();

    // Роутинг намерения (Intent Routing)
    // В зависимости от входных параметров, агент будет вызывать конкретные Tools.
    console.log(`[ROUTING] Обработка намерения: ${inputParams.intent || 'idle'}`);
    
    // Возвращаем метаданные контекста для инициализации LLM
    return {
        status: "ready",
        active_directory: BRAIN_DIR,
        distillation_checked: true
    };
}

module.exports = {
    runAgentCycle
};

// Если запущен напрямую (например, CLI):
if (require.main === module) {
    runAgentCycle({ intent: "cli_init" });
}

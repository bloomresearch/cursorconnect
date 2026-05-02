const readline = require("readline");

let Agent;
try {
    const sdk = require("@cursor/sdk");
    Agent = sdk.Agent;
} catch (e) {
    if (e.code === "ERR_REQUIRE_ESM") {
        // Fallback for ESM if needed, though this will be async.
        // For simplicity we fail and print an error here, 
        // as standard commonjs or compiled TS is expected.
        console.error(JSON.stringify({ error: "Please run with ESM or compile to CJS" }));
        process.exit(1);
    }
    console.error(JSON.stringify({ error: "Could not load @cursor/sdk" }));
    process.exit(1);
}

const agents = new Map();
const runs = new Map();
let nextId = 1;

function sendResponse(id, type, data) {
    if (type === "error") {
        console.log(JSON.stringify({ 
            id, 
            type: "error", 
            error: data instanceof Error ? data.message : String(data) 
        }));
    } else {
        console.log(JSON.stringify({ id, type, data }));
    }
}

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

rl.on("line", async (line) => {
    if (!line.trim()) return;
    try {
        const req = JSON.parse(line);
        const { id, action, target, args = [] } = req;
        
        if (!id || !action) {
            sendResponse(id || "unknown", "error", "Missing id or action");
            return;
        }

        try {
            if (action === "Agent.create") {
                const [options] = args;
                const agent = await Agent.create(options);
                const agentId = `agent_${nextId++}`;
                agents.set(agentId, agent);
                sendResponse(id, "success", { agentId });
                
            } else if (action === "agent.send") {
                const agent = agents.get(target);
                if (!agent) throw new Error(`Agent not found: ${target}`);
                
                const [prompt, options = {}] = args;
                
                // Convert stream event flags into callbacks if passed
                if (options.streamEvents) {
                    options.onDelta = (updateArgs) => {
                        sendResponse(id, "event", { type: "delta", update: updateArgs.update });
                    };
                    options.onStep = (stepArgs) => {
                        sendResponse(id, "event", { type: "step", step: stepArgs.step });
                    };
                    delete options.streamEvents;
                }
                
                const run = await agent.send(prompt, options);
                const runId = `run_${nextId++}`;
                runs.set(runId, run);
                sendResponse(id, "success", { runId });
                
            } else if (action === "run.wait") {
                const run = runs.get(target);
                if (!run) throw new Error(`Run not found: ${target}`);
                const result = await run.wait();
                sendResponse(id, "success", result);
                
            } else if (action === "run.cancel") {
                const run = runs.get(target);
                if (!run) throw new Error(`Run not found: ${target}`);
                await run.cancel();
                sendResponse(id, "success", true);
                
            } else if (action === "run.conversation") {
                const run = runs.get(target);
                if (!run) throw new Error(`Run not found: ${target}`);
                const conv = await run.conversation();
                sendResponse(id, "success", conv);
                
            } else if (action === "run.stream") {
                const run = runs.get(target);
                if (!run) throw new Error(`Run not found: ${target}`);
                
                if (typeof run.stream === "function") {
                    for await (const update of run.stream()) {
                        sendResponse(id, "yield", update);
                    }
                } else if (run.stream && typeof run.stream[Symbol.asyncIterator] === "function") {
                    for await (const update of run.stream) {
                        sendResponse(id, "yield", update);
                    }
                } else {
                    throw new Error("run.stream is not an async iterable");
                }
                sendResponse(id, "success", null);
                
            } else if (action === "agent.close") {
                const agent = agents.get(target);
                if (!agent) throw new Error(`Agent not found: ${target}`);
                if (typeof agent.close === "function") {
                    await agent.close(...args);
                }
                sendResponse(id, "success", true);
                
            } else if (action === "agent.reload") {
                const agent = agents.get(target);
                if (!agent) throw new Error(`Agent not found: ${target}`);
                if (typeof agent.reload === "function") {
                    await agent.reload(...args);
                }
                sendResponse(id, "success", true);
                
            } else {
                throw new Error(`Unknown action: ${action}`);
            }
        } catch (err) {
            sendResponse(id, "error", err);
        }
    } catch (parseErr) {
        sendResponse("unknown", "error", "Invalid JSON");
    }
});

// Handle graceful shutdown on stdin close
rl.on("close", () => {
    process.exit(0);
});

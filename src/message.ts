export interface Message{
    role: "user" | "assistant";
    text: string;

}

export const msgHistory:Message[]=[]
import { ChatShell } from "@/components/ChatShell";

export default function ConversationPage({ params }: { params: { id: string } }) {
  return <ChatShell initialConversationId={params.id} />;
}

// hooks/useDocumentWatcher.js
import { useEffect } from 'react';

export function useDocumentWatcher(onNewDocument) {
    useEffect(() => {
        let ws;
        let reconnectTimer;

        function connect() {
            ws = new WebSocket('ws://localhost:8000/ws/documents');

            ws.onopen = () => {
                console.log('🔌 WebSocket connecté — surveillance active');
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'new_document') {
                    onNewDocument(data);
                }
            };

            ws.onclose = () => {
                console.log('🔌 WebSocket déconnecté — reconnexion dans 3s');
                reconnectTimer = setTimeout(connect, 3000);
            };

            ws.onerror = () => ws.close();
        }

        connect();

        return () => {
            clearTimeout(reconnectTimer);
            if (ws) ws.close();
        };
    }, [onNewDocument]);
}
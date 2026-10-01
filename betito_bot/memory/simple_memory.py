from collections import deque


class SimpleMemory():
    def __init__(self, max_messages:int=10):
        self.history = deque(maxlen=max_messages)

    def add(self, role: str, text:str):
        self.history.append({"role":role, "content":text})

    #Obtener todos los mensajes.
    def messages(self):
        return list(self.history)

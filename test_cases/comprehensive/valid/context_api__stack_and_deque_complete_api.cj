main(): Unit { let stack: ArrayStack<Int64> = ArrayStack<Int64>()
 let reservedStack: ArrayStack<Int64> = ArrayStack<Int64>(8)
 stack.add(1)
 let stackTop: Optional<Int64> = stack.peek()
 let stackRemoved: Optional<Int64> = stack.remove()
 let stackEmpty: Bool = stack.isEmpty()
 stack.reserve(16)
 let stackValues: Array<Int64> = stack.toArray()
 let stackSize: Int64 = stack.size
 let stackCapacity: Int64 = stack.capacity
 stack.clear()
 let stackContract: Stack<Int64> = stack
 stackContract.add(2)
 stackContract.peek()
 stackContract.remove()
 let deque: ArrayDeque<Int64> = ArrayDeque<Int64>()
 let reservedDeque: ArrayDeque<Int64> = ArrayDeque<Int64>(8)
 deque.addFirst(1)
 deque.addLast(2)
 let dequeFirst: Optional<Int64> = deque.removeFirst()
 let dequeLast: Optional<Int64> = deque.removeLast()
 let dequeEmpty: Bool = deque.isEmpty()
 deque.reserve(16)
 let dequeValues: Array<Int64> = deque.toArray()
 let dequeSize: Int64 = deque.size
 let dequeCapacity: Int64 = deque.capacity
 deque.clear()
 let dequeContract: Deque<Int64> = deque
 dequeContract.addFirst(3)
 dequeContract.addLast(4)
 dequeContract.removeFirst()
 dequeContract.removeLast() }

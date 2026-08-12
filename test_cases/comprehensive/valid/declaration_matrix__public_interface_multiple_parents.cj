interface Left {}
interface Right {}
public interface Both<T> <: Left & Right { func id(value: T): T; }
main(): Unit {}

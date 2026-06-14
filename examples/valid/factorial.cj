func factorial(n: Int32): Int32 {
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}

func main() {
    var result = factorial(5)
    if result == 120 {
        return
    }
}

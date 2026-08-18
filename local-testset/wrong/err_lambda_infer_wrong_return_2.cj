func outer(f: (Int64) -> (Int64) -> Int64): Int64 {
    f(0)(1)
}

func ident(n: Int64): Int64 {
    n
}

func add(a: Int64, b: Int64): Int64 {
    a + b
}

func mul(a: Int64, b: Int64): Int64 {
    a * b
}

func sub(a: Int64, b: Int64): Int64 {
    a - b
}

func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(a: Int64, b: Int64): Int64 {
    a + b
}

func padDelta(s: String): String {
    s
}

func padEpsilon(flag: Bool): Bool {
    flag
}

func padZeta(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func padEta(n: Int64): Int64 {
    if (n < 0) {
        0
    } else {
        n
    }
}

main(): Unit {
    println("ident=" + (ident(5)).toString())
    println("add=" + (add(1, 2)).toString())
    println("mul=" + (mul(3, 4)).toString())
    println("sub=" + (sub(9, 2)).toString())
    println("pad=" + (padAlpha()).toString())
    let out: Int64 = outer({ a: Int64 => { b: Int64 => "x" } })
    println((out).toString())
}

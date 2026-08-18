import std.collection.*

func mkEmpty(): ArrayList<Int64> {
    ArrayList<Int64>()
}

func listSize(a: ArrayList<Int64>): Int64 {
    a.size
}

func pushOne(a: ArrayList<Int64>): Unit {
    a.add(7)
}

func peek0(a: ArrayList<Int64>): Int64 {
    a[0]
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
    let a: ArrayList<Int64> = mkEmpty()
    println("start=" + (listSize(a)).toString())
    pushOne(a)
    println("afterPush=" + (listSize(a)).toString())
    println("peek=" + (peek0(a)).toString())
    println("pad=" + (padAlpha()).toString())
    a.add("x")
    println((a.size).toString())
}
